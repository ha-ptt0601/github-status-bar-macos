import os
import plistlib
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

from chip import installer


class InstallTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        tmp = Path(self.tmpdir.name)
        self.home, self.repo, self.plugin_dir = tmp / "home", tmp / "repo", tmp / "plugins"
        (self.repo / "bin").mkdir(parents=True)
        (self.repo / "bin" / "chip").write_text("#!/usr/bin/env python3\n")
        (self.repo / "skill").mkdir()
        (self.repo / "skill" / "SKILL.md").write_text("---\nname: chip\n---\nrun `{{CHIP}} menu`\n")
        (self.repo / "app").mkdir()
        (self.repo / "chip" / "assets").mkdir(parents=True)
        (self.repo / "chip" / "assets" / "github-mark.svg").write_text("<svg/>")
        self.config = tmp / "config.json"
        self.calls, self.out = [], []
        self.mcp_registered = ""
        self.tools = {"gh", "claude", "git", "python3", "fzf", "swift"}
        self.defaults_dir = self.plugin_dir
        self.build_fails = False

    def tearDown(self):
        self.tmpdir.cleanup()

    @property
    def chip_bin(self):
        return self.repo / "bin" / "chip"

    @property
    def app(self):
        return self.home / "Applications" / "GitHubBar.app"

    def runner(self, cmd, **kw):
        self.calls.append(cmd)
        if cmd[:3] == ["defaults", "read", "com.ameba.SwiftBar"]:
            if self.defaults_dir is None:
                return subprocess.CompletedProcess(cmd, 1, "", "does not exist")
            return subprocess.CompletedProcess(cmd, 0, f"{self.defaults_dir}\n", "")
        if cmd[:3] == ["claude", "mcp", "get"]:
            code = 0 if self.mcp_registered else 1
            return subprocess.CompletedProcess(cmd, code, self.mcp_registered, "")
        if cmd[:2] == ["swift", "build"]:
            if self.build_fails:
                return subprocess.CompletedProcess(cmd, 1, "", "error: boom")
            binary = self.repo / "app" / ".build" / "release" / "GitHubBar"
            binary.parent.mkdir(parents=True, exist_ok=True)
            binary.write_text("binary")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    def which(self, name):
        return f"/opt/bin/{name}" if name in self.tools else None

    def install(self):
        return installer.install(self.repo, self.home, runner=self.runner, which=self.which,
                                 out=self.out.append, env={"PATH": str(self.home / ".local" / "bin")},
                                 config_file=self.config)

    def test_installs_link_skill_mcp_config(self):
        self.assertEqual(self.install(), 0)
        self.assertEqual((self.home / ".local" / "bin" / "chip").resolve(), self.chip_bin.resolve())
        skill = (self.home / ".claude" / "skills" / "chip" / "SKILL.md").read_text()
        self.assertIn(f"run `{self.chip_bin} menu`", skill)
        self.assertIn(installer.MARKER, skill)
        self.assertIn(["claude", "mcp", "add", "--scope", "user", "chip", "--", str(self.chip_bin), "mcp"],
                      self.calls)
        self.assertTrue(self.config.exists())

    def test_builds_and_bundles_githubbar(self):
        self.install()
        self.assertIn(["swift", "build", "-c", "release", "--package-path", str(self.repo / "app")], self.calls)
        binary = self.app / "Contents" / "MacOS" / "GitHubBar"
        self.assertEqual(binary.read_text(), "binary")
        self.assertTrue(binary.stat().st_mode & stat.S_IXUSR)
        info = plistlib.loads((self.app / "Contents" / "Info.plist").read_bytes())
        self.assertEqual((info["CFBundleName"], info["CFBundleDisplayName"]), ("GitHubBar", "GitHubBar"))
        self.assertEqual(info["CFBundleIdentifier"], installer.BUNDLE_ID)
        self.assertTrue(info["LSUIElement"])
        self.assertEqual(info["LSEnvironment"]["CHIP_PLUGIN"], str(self.chip_bin))
        self.assertIn("/opt/bin", info["LSEnvironment"]["PATH"])
        self.assertIn(["codesign", "--force", "--sign", "-", str(self.app)], self.calls)
        self.assertIn(["xattr", "-dr", "com.apple.quarantine", str(self.app)], self.calls)
        self.assertIn(["open", str(self.app)], self.calls)
        self.assertTrue(any(c[:2] == ["iconutil", "-c"] for c in self.calls))
        self.assertFalse(any(c[0] == "osascript" and "System Events" in c[-1] for c in self.calls))

    def test_without_swift_skips_the_app(self):
        self.tools.discard("swift")
        self.assertEqual(self.install(), 0)
        self.assertFalse(self.app.exists())
        self.assertTrue(any("xcode-select --install" in line for line in self.out))

    def test_build_failure_is_reported(self):
        self.build_fails = True
        self.assertEqual(self.install(), 1)
        self.assertFalse(self.app.exists())
        self.assertTrue(any("boom" in line for line in self.out))

    def test_removes_chip_swiftbar_plugins_only(self):
        self.plugin_dir.mkdir()
        for name in ("chip.1m.sh", "chip.3m.sh", "chip-mine.1m.sh"):
            (self.plugin_dir / name).write_text(f"#!/bin/bash\n# {installer.MARKER}\n")
        (self.plugin_dir / "weather.5m.sh").write_text("#!/bin/sh\necho sun\n")
        (self.plugin_dir / "chip.1m.sh.bak").write_text("keep")
        self.install()
        self.assertEqual(sorted(p.name for p in self.plugin_dir.iterdir()), ["chip.1m.sh.bak", "weather.5m.sh"])

    def test_second_install_is_idempotent(self):
        self.install()
        self.mcp_registered = f"chip:\n  Command: {self.chip_bin}\n  Args: mcp\n"
        self.calls.clear()
        self.assertEqual(self.install(), 0)
        self.assertFalse(any(c[:3] == ["claude", "mcp", "add"] for c in self.calls))

    def test_foreign_files_are_left_alone(self):
        link = self.home / ".local" / "bin" / "chip"
        link.parent.mkdir(parents=True)
        link.symlink_to("/somewhere/else")
        skill_dir = self.home / ".claude" / "skills" / "chip"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("someone else's skill")
        self.plugin_dir.mkdir()
        (self.plugin_dir / "chip.1m.sh").write_text("#!/bin/sh\necho mine\n")
        self.mcp_registered = "chip:\n  Command: /other/chip\n"
        self.install()
        self.assertEqual(os.readlink(link), "/somewhere/else")
        self.assertEqual((skill_dir / "SKILL.md").read_text(), "someone else's skill")
        self.assertIn("echo mine", (self.plugin_dir / "chip.1m.sh").read_text())
        self.assertGreaterEqual(sum("skip" in line for line in self.out), 3)

    def test_dev_symlink_skill_is_replaced(self):
        skill_dir = self.home / ".claude" / "skills" / "chip"
        skill_dir.parent.mkdir(parents=True)
        skill_dir.symlink_to(self.repo / "skill")
        self.install()
        self.assertFalse(skill_dir.is_symlink())
        self.assertIn(str(self.chip_bin), (skill_dir / "SKILL.md").read_text())

    def test_missing_prerequisite_stops_before_writing(self):
        self.tools.discard("gh")
        self.assertEqual(self.install(), 1)
        self.assertFalse((self.home / ".local").exists())
        self.assertTrue(any("gh" in line for line in self.out))

    def test_uninstall_removes_only_ours(self):
        self.install()
        self.mcp_registered = f"chip:\n  Command: {self.chip_bin}\n"
        installer.uninstall(self.repo, self.home, runner=self.runner, out=self.out.append)
        self.assertFalse((self.home / ".local" / "bin" / "chip").exists())
        self.assertFalse((self.home / ".claude" / "skills" / "chip").exists())
        self.assertFalse(self.app.exists())
        self.assertIn(["claude", "mcp", "remove", "chip", "--scope", "user"], self.calls)
        self.assertTrue(any(c[0] == "osascript" and "delete login item" in c[-1] for c in self.calls))
        self.assertTrue(self.config.exists())
