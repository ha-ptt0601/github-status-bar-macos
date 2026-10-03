import json
import subprocess
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from chip import runs

ROW = {"label": "api#2069", "title": "update(newsletter)", "url": "https://github.com/acme/api/pull/2069",
       "repo": "acme/api", "number": 2069}
CFG = {"permission_mode": "auto", "disallowed_tools": ["Edit", "Write", "NotebookEdit"]}
SKILL = {"name": "Full review", "prompt": "/my-review-skill {url}"}


def done(cmd, stdout="", code=0, stderr=""):
    return subprocess.CompletedProcess(cmd, code, stdout, stderr)


class CommandTest(unittest.TestCase):
    def test_prompt_first_and_comma_joined_tools(self):
        self.assertEqual(runs.build_command("/x", "api#1", "Full review", CFG), [
            "claude", "/x", "--bg", "--name", "chip · api#1 · Full review",
            "--permission-mode", "auto", "--disallowedTools", "Edit,Write,NotebookEdit"])

    def test_no_disallowed_tools(self):
        cmd = runs.build_command("/x", "a#1", "S", {"permission_mode": "auto", "disallowed_tools": []})
        self.assertNotIn("--disallowedTools", cmd)

    def test_parse_bg_id(self):
        self.assertEqual(runs.parse_bg_id("backgrounded · b19aff59 · chip · api#1 · S\n  claude agents"), "b19aff59")
        self.assertIsNone(runs.parse_bg_id("error: nope"))


class StartTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "runs.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_start_records_run(self):
        calls = []

        def runner(cmd, **kw):
            calls.append((cmd, kw.get("cwd")))
            return done(cmd, "backgrounded · ab12cd34 · x\n")

        record = runs.start(ROW, SKILL, CFG, "/src/api", self.path, runner=runner, now=lambda: 100.0)
        self.assertEqual(calls[0][1], "/src/api")
        self.assertEqual(calls[0][0][1], "/my-review-skill https://github.com/acme/api/pull/2069")
        self.assertEqual(record["id"], "ab12cd34")
        saved = runs.load(self.path)["api#2069::Full review"]
        self.assertEqual((saved["started_at"], saved["skill"], saved["label"]), (100.0, "Full review", "api#2069"))

    def test_start_failure(self):
        with self.assertRaisesRegex(runs.RunError, "boom"):
            runs.start(ROW, SKILL, CFG, "/src", self.path, runner=lambda cmd, **kw: done(cmd, "", 1, "boom"))
        self.assertEqual(runs.load(self.path), {})


class StatusTest(unittest.TestCase):
    def test_view_states(self):
        rec = {"id": "ab", "started_at": 0}
        self.assertEqual(runs.view(rec, {"state": "working"}, 125), {"kind": "running", "text": "running 2m"})
        self.assertEqual(runs.view(rec, {"state": "blocked"}, 1), {"kind": "needs_you", "text": "needs you"})
        self.assertEqual(runs.view(rec, None, 1), {"kind": "gone", "text": "session gone"})
        self.assertEqual(runs.view(rec, {"state": "weird", "status": "idle"}, 1), {"kind": "other", "text": "weird"})

    def test_done_text_uses_done_at(self):
        rec = {"id": "a", "started_at": 0, "done_at": datetime(2026, 10, 3, 11, 40).timestamp()}
        self.assertEqual(runs.view(rec, {"state": "done"}, 0)["text"], "done 11:40")

    def test_format_elapsed(self):
        self.assertEqual(runs.format_elapsed(10), "1m")
        self.assertEqual(runs.format_elapsed(3720), "1h02m")

    def test_observe_stamps_done_once_and_clears_on_resume(self):
        records = {"k": {"id": "ab", "started_at": 0}}
        self.assertTrue(runs.observe(records, {"ab": {"state": "done"}}, 50))
        self.assertFalse(runs.observe(records, {"ab": {"state": "done"}}, 60))
        self.assertEqual(records["k"]["done_at"], 50)
        self.assertTrue(runs.observe(records, {"ab": {"state": "working"}}, 70))
        self.assertNotIn("done_at", records["k"])

    def test_fetch_agents(self):
        out = json.dumps([{"id": "ab", "state": "done"}, {"name": "no id"}])
        self.assertEqual(runs.fetch_agents(lambda cmd, **kw: done(cmd, out)), {"ab": {"id": "ab", "state": "done"}})
        self.assertEqual(runs.fetch_agents(lambda cmd, **kw: done(cmd, "", 1)), {})
        self.assertEqual(runs.fetch_agents(lambda cmd, **kw: done(cmd, "not json")), {})

    def test_find_by_id(self):
        records = {"k": {"id": "ab"}}
        self.assertEqual(runs.find_by_id(records, "ab"), ("k", {"id": "ab"}))
        self.assertIsNone(runs.find_by_id(records, "zz"))
