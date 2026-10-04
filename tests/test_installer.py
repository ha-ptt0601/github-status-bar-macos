import os
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
        self.app = tmp / "SwiftBar.app"
        self.config = tmp / "config.json"
        self.calls, self.out = [], []
        self.mcp_registered = ""
        self.tools = {"gh", "claude", "git", "python3", "fzf"}
        self.defaults_dir = self.plugin_dir

    def tearDown(self):
        self.tmpdir.cleanup()

    @property
    def chip_bin(self):
        return self.repo / "bin" / "chip"

    def runner(self, cmd, **kw):
        self.calls.append(cmd)
        if cmd[:3] == ["defaults", "read", "com.ameba.SwiftBar"]:
            if self.defaults_dir is None:
                return subprocess.CompletedProcess(cmd, 1, "", "does not exist")
            return subprocess.CompletedProcess(cmd, 0, f"{self.defaults_dir}\n", "")
        if cmd[:3] == ["claude", "mcp", "get"]:
            code = 0 if self.mcp_registered else 1
            return subprocess.CompletedProcess(cmd, code, self.mcp_registered, "")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    def which(self, name):
        return f"/opt/bin/{name}" if name in self.tools else None

    def install(self):
        return installer.install(self.repo, self.home, runner=self.runner, which=self.which,
                                 out=self.out.append, env={"PATH": str(self.home / ".local" / "bin")},
                                 swiftbar_app=self.app, config_file=self.config)

    def test_installs_everything(self):
        self.assertEqual(self.install(), 0)
        link = self.home / ".local" / "bin" / "chip"
        self.assertEqual(link.resolve(), self.chip_bin.resolve())
        skill = (self.home / ".claude" / "skills" / "chip" / "SKILL.md").read_text()
        self.assertIn(f"run `{self.chip_bin} menu`", skill)
        self.assertIn(installer.MARKER, skill)
        self.assertIn(["claude", "mcp", "add", "--scope", "user", "chip", "--", str(self.chip_bin), "mcp"],
                      self.calls)
        plugin = self.plugin_dir / installer.PLUGIN_NAME
        text = plugin.read_text()
        self.assertIn(f'exec "{self.chip_bin}" swiftbar', text)
        self.assertIn("/opt/bin", text)
        self.assertTrue(plugin.stat().st_mode & stat.S_IXUSR)
        self.assertTrue(self.config.exists())

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
        (self.plugin_dir / installer.PLUGIN_NAME).write_text("#!/bin/sh\necho mine\n")
        self.mcp_registered = "chip:\n  Command: /other/chip\n"
        self.install()
        self.assertEqual(os.readlink(link), "/somewhere/else")
        self.assertEqual((skill_dir / "SKILL.md").read_text(), "someone else's skill")
        self.assertIn("echo mine", (self.plugin_dir / installer.PLUGIN_NAME).read_text())
        self.assertGreaterEqual(sum("skip" in line for line in self.out), 4)

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
        self.assertFalse((self.plugin_dir / installer.PLUGIN_NAME).exists())
        self.assertIn(["claude", "mcp", "remove", "chip", "--scope", "user"], self.calls)
        self.assertTrue(self.config.exists())

    def test_refreshes_every_minute_and_removes_legacy_plugin(self):
        self.assertEqual(installer.PLUGIN_NAME, "chip.1m.sh")
        self.plugin_dir.mkdir()
        legacy = self.plugin_dir / "chip.3m.sh"
        legacy.write_text(f"#!/bin/bash\n# {installer.MARKER}\n")
        self.install()
        self.assertFalse(legacy.exists())
        self.assertTrue((self.plugin_dir / "chip.1m.sh").exists())

    def test_foreign_legacy_name_is_kept(self):
        self.plugin_dir.mkdir()
        legacy = self.plugin_dir / "chip.3m.sh"
        legacy.write_text("#!/bin/sh\necho mine\n")
        self.install()
        self.assertTrue(legacy.exists())

    def test_unset_plugin_dir_uses_dot_swiftbar(self):
        self.defaults_dir = None
        self.install()
        expected = self.home / ".swiftbar"
        self.assertTrue((expected / installer.PLUGIN_NAME).exists())
        self.assertIn(["defaults", "write", "com.ameba.SwiftBar", "PluginDirectory", str(expected)], self.calls)

    def test_moves_off_swiftbar_data_folder(self):
        data_dir = self.home / "Library" / "Application Support" / "SwiftBar" / "Plugins"
        data_dir.mkdir(parents=True)
        (data_dir / "chip.3m.sh").write_text(f"#!/bin/bash\n# {installer.MARKER}\n")
        self.defaults_dir = data_dir
        self.app.mkdir()
        self.install()
        new_dir = self.home / ".swiftbar"
        self.assertTrue((new_dir / installer.PLUGIN_NAME).exists())
        self.assertFalse((data_dir / "chip.3m.sh").exists())
        self.assertIn(["defaults", "write", "com.ameba.SwiftBar", "PluginDirectory", str(new_dir)], self.calls)
        self.assertIn(["killall", "SwiftBar"], self.calls)
