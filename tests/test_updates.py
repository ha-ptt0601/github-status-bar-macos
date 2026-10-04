import subprocess
import tempfile
import unittest
from pathlib import Path

from chip import updates


def done(cmd, stdout="", code=0, stderr=""):
    return subprocess.CompletedProcess(cmd, code, stdout, stderr)


class VersionTest(unittest.TestCase):
    def test_parse_and_compare(self):
        self.assertEqual(updates.parse_version("v1.2.10"), (1, 2, 10))
        self.assertTrue(updates.is_newer("0.10.0", "0.9.9"))
        self.assertFalse(updates.is_newer("0.1.0", "0.1.0"))
        self.assertFalse(updates.is_newer("garbage", "0.1.0"))

    def test_read_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "chip").mkdir()
            (Path(tmp) / "chip" / "__init__.py").write_text('__version__ = "0.3.1"\n')
            self.assertEqual(updates.read_version(Path(tmp)), "0.3.1")


class LatestReleaseTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "update.json"
        self.calls = []

    def tearDown(self):
        self.tmp.cleanup()

    def runner(self, cmd, **kw):
        self.calls.append(cmd)
        return done(cmd, "v0.4.0\n")

    def test_checks_then_caches_for_six_hours(self):
        self.assertEqual(updates.latest_release(self.path, self.runner, now=1000), "0.4.0")
        self.assertEqual(self.calls[0], ["gh", "api", f"repos/{updates.REPO}/releases/latest", "--jq", ".tag_name"])
        self.assertEqual(updates.latest_release(self.path, self.runner, now=1000 + 3600), "0.4.0")
        self.assertEqual(len(self.calls), 1)
        updates.latest_release(self.path, self.runner, now=1000 + 7 * 3600)
        self.assertEqual(len(self.calls), 2)
        updates.latest_release(self.path, self.runner, now=1000 + 7 * 3600 + 1, force=True)
        self.assertEqual(len(self.calls), 3)

    def test_no_release_is_none_and_cached(self):
        runner = lambda cmd, **kw: self.calls.append(cmd) or done(cmd, "", 1, "Not Found")
        self.assertIsNone(updates.latest_release(self.path, runner, now=10))
        self.assertIsNone(updates.latest_release(self.path, runner, now=20))
        self.assertEqual(len(self.calls), 1)


class UpdateRepoTest(unittest.TestCase):
    def script(self, status_out="", pull=(0, "Updating 1..2", "")):
        def runner(cmd, **kw):
            if "status" in cmd:
                return done(cmd, status_out)
            return done(cmd, pull[1], pull[0], pull[2])
        return runner

    def test_dirty_tree_stops(self):
        ok, message = updates.update_repo("/r", self.script(status_out=" M chip/cli.py\n"))
        self.assertFalse(ok)
        self.assertIn("local changes", message)

    def test_fast_forward(self):
        self.assertEqual(updates.update_repo("/r", self.script()), (True, "Updating 1..2"))

    def test_pull_failure(self):
        ok, message = updates.update_repo("/r", self.script(pull=(1, "", "Not possible to fast-forward")))
        self.assertFalse(ok)
        self.assertIn("fast-forward", message)
