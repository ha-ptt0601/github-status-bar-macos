import subprocess
import tempfile
import unittest
from pathlib import Path

from chip import model, notify

ROWS = [
    {"label": "api#1", "status": model.NEW, "title": "t1", "author": "alice"},
    {"label": "api#2", "status": model.REREVIEW, "title": "t2", "author": "an"},
]
KEY = "api#1::Full review"
RECORDS = {KEY: {"label": "api#1", "skill": "Full review"}}


class DiffTest(unittest.TestCase):
    def test_first_run_is_silent(self):
        self.assertEqual(notify.diff(None, notify.snapshot(ROWS, {}, None), ROWS, {}), [])

    def test_new_pr_and_rereview(self):
        prev = notify.snapshot([], {}, None)
        prev["prs"] = {"api#2": model.WAITING}
        self.assertEqual(notify.diff(prev, notify.snapshot(ROWS, {}, None), ROWS, {}),
                         ["New review request: api#1 — t1 by alice", "Needs re-review: api#2 — t2"])

    def test_unchanged_is_silent(self):
        cur = notify.snapshot(ROWS, {}, None)
        self.assertEqual(notify.diff(cur, cur, ROWS, {}), [])

    def test_run_transitions(self):
        prev = notify.snapshot(ROWS, {KEY: {"kind": "running"}}, None)
        done = notify.snapshot(ROWS, {KEY: {"kind": "done"}}, None)
        self.assertEqual(notify.diff(prev, done, ROWS, RECORDS), ["Review finished: api#1 (Full review)"])
        blocked = notify.snapshot(ROWS, {KEY: {"kind": "needs_you"}}, None)
        self.assertEqual(notify.diff(prev, blocked, ROWS, RECORDS), ["Review needs you: api#1 (Full review)"])

    def test_update_announced_once(self):
        prev = notify.snapshot(ROWS, {}, None)
        cur = notify.snapshot(ROWS, {}, "0.4.0")
        self.assertEqual(notify.diff(prev, cur, ROWS, {}), ["GitHubBar v0.4.0 is available"])
        self.assertEqual(notify.diff(cur, cur, ROWS, {}), [])

    def test_long_titles_are_cut(self):
        rows = [{"label": "api#9", "status": model.NEW, "title": "x" * 80, "author": "a"}]
        prev = notify.snapshot([], {}, None)
        message = notify.diff(prev, notify.snapshot(rows, {}, None), rows, {})[0]
        self.assertIn("x" * 59 + "…", message)

    def test_cap(self):
        self.assertEqual(notify.cap(["a", "b", "c", "d", "e"]), ["a", "b", "c", "+2 more"])
        self.assertEqual(notify.cap(["a"]), ["a"])


class SendAndStateTest(unittest.TestCase):
    def test_send_escapes_quotes(self):
        calls = []
        notify.send(['say "hi"'], runner=lambda cmd, **kw: calls.append(cmd) or subprocess.CompletedProcess(cmd, 0))
        self.assertEqual(calls, [["osascript", "-e", 'display notification "say \\"hi\\"" with title "chip"']])

    def test_load_save_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "notify.json"
            self.assertIsNone(notify.load(path))
            notify.save(path, {"prs": {}, "runs": {}, "update": ""})
            self.assertEqual(notify.load(path), {"prs": {}, "runs": {}, "update": ""})


class MineNotifyTest(unittest.TestCase):
    def mine(self, status=model.AWAITING, reviewers=None, times=None):
        return {"label": "api#7", "title": "t7", "mine_status": status,
                "reviewers": reviewers or {}, "review_times": times or {}}

    def diff(self, before, after):
        prev = notify.snapshot(ROWS, {}, None, [before])
        cur = notify.snapshot(ROWS, {}, None, [after])
        return notify.diff(prev, cur, ROWS, {})

    def test_reviewer_events(self):
        before = self.mine()
        self.assertEqual(self.diff(before, self.mine(model.READY, {"bob": "APPROVED"}, {"bob": "t1"})),
                         ["bob approved api#7 — t7"])
        self.assertEqual(self.diff(before, self.mine(model.CHANGES, {"bob": "CHANGES_REQUESTED"}, {"bob": "t1"})),
                         ["bob requested changes on api#7 — t7"])

    def test_second_comment_from_same_reviewer(self):
        before = self.mine(model.THREADS, {"carol": "COMMENTED"}, {"carol": "t1"})
        after = self.mine(model.THREADS, {"carol": "COMMENTED"}, {"carol": "t2"})
        self.assertEqual(self.diff(before, after), ["carol commented on api#7 — t7"])

    def test_ci_failed_and_conflict(self):
        self.assertEqual(self.diff(self.mine(), self.mine(model.CI_FAILED)), ["CI failed on api#7 — t7"])
        self.assertEqual(self.diff(self.mine(), self.mine(model.CONFLICT)), ["Conflict on api#7 — t7"])

    def test_new_own_pr_and_old_snapshot_are_silent(self):
        cur = notify.snapshot(ROWS, {}, None, [self.mine(model.CHANGES, {"a": "CHANGES_REQUESTED"}, {"a": "t"})])
        self.assertEqual(notify.diff(notify.snapshot(ROWS, {}, None, []), cur, ROWS, {}), [])
        old = notify.snapshot(ROWS, {}, None)
        del old["mine"]
        self.assertEqual(notify.diff(old, cur, ROWS, {}), [])


class EventsTest(unittest.TestCase):
    def test_events_carry_links(self):
        rows = [dict(r, url=f"https://x/{r['label']}") for r in ROWS]
        prev = notify.snapshot([], {KEY: {"kind": "running"}}, None)
        cur = notify.snapshot(rows, {KEY: {"kind": "done"}}, "0.2.0")
        records = {KEY: dict(RECORDS[KEY], id="ab")}
        found = notify.events(prev, cur, rows, records)
        self.assertEqual(found[0], {"text": "New review request: api#1 — t1 by alice", "href": "https://x/api#1"})
        self.assertEqual(found[2], {"text": "Review finished: api#1 (Full review)", "run": "ab"})
        self.assertEqual(found[3]["href"], notify.RELEASES_URL)

    def test_cap_events(self):
        self.assertEqual(notify.cap([{"text": str(i)} for i in range(5)], 2)[-1], {"text": "+3 more"})


class StorageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_history_is_newest_first_and_capped(self):
        path = self.dir / "history.json"
        notify.remember(path, [{"text": "a"}], 1, limit=2)
        notify.remember(path, [{"text": "b"}, {"text": "c"}], 2, limit=2)
        self.assertEqual(notify.load_list(path), [{"text": "b", "at": 2}, {"text": "c", "at": 2}])

    def test_outbox_queue_and_drain(self):
        path = self.dir / "outbox.json"
        notify.queue(path, [{"text": "a"}])
        notify.queue(path, [{"text": "b"}])
        self.assertEqual(notify.drain(path), [{"text": "a"}, {"text": "b"}])
        self.assertEqual(notify.drain(path), [])
