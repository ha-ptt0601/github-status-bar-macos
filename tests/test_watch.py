import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from chip import watch


def response(status, body="", poll=60, last_modified="Sun, 04 Oct 2026 09:55:33 GMT"):
    reason = {200: "OK", 304: "Not Modified"}.get(status, "Error")
    head = f"HTTP/2.0 {status} {reason}\r\nX-Poll-Interval: {poll}\r\nLast-Modified: {last_modified}\r\n"
    return head + "\r\n" + body


def note(updated, reason="review_requested", kind="PullRequest"):
    return {"updated_at": updated, "reason": reason, "subject": {"type": kind}}


class CheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "notifications.json"
        self.calls, self.replies = [], []

    def tearDown(self):
        self.tmp.cleanup()

    def runner(self, cmd, **kw):
        self.calls.append(cmd)
        status, body = self.replies.pop(0)
        return subprocess.CompletedProcess(cmd, 0 if status == 200 else 1, response(status, body), "")

    def check(self, now):
        return watch.check(self.path, self.runner, now)

    def test_first_check_only_records_then_new_pr_notification_triggers(self):
        self.replies = [(200, json.dumps([note("2026-10-04T09:00:00Z")]))]
        self.assertFalse(self.check(1000))  # first look: remember, no fetch
        self.assertFalse(self.check(1030))  # too early (poll interval 60 s): no request
        self.assertEqual(len(self.calls), 1)
        self.replies = [(304, "")]
        self.assertFalse(self.check(1061))
        self.assertIn("If-Modified-Since: Sun, 04 Oct 2026 09:55:33 GMT", self.calls[-1])
        self.replies = [(200, json.dumps([note("2026-10-04T09:10:00Z"), note("2026-10-04T09:00:00Z")]))]
        self.assertTrue(self.check(1122))
        self.replies = [(200, json.dumps([note("2026-10-04T09:10:00Z")]))]
        self.assertFalse(self.check(1183))  # nothing newer than last seen

    def test_irrelevant_notifications_do_not_trigger(self):
        self.replies = [(200, "[]"), (200, json.dumps([note("2026-10-04T09:10:00Z", kind="Issue"),
                                                       note("2026-10-04T09:11:00Z", reason="security_alert")]))]
        self.check(1000)
        self.assertFalse(self.check(1100))

    def test_unavailable_returns_none_and_backs_off(self):
        self.replies = [(403, '{"message": "Resource not accessible"}')]
        self.assertIsNone(self.check(1000))
        self.assertIsNone(self.check(1100))  # still backing off, no new request
        self.assertEqual(len(self.calls), 1)

    def test_parse_response(self):
        status, headers, body = watch.parse_response(response(200, "[1]", poll=90))
        self.assertEqual((status, headers["x-poll-interval"], body), (200, "90", "[1]"))
        self.assertEqual(watch.parse_response("garbage")[0], 0)
