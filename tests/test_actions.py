import json
import subprocess
import unittest

from chip import actions

REVIEW = {"label": "api#7", "title": "fix: thing", "url": "https://github.com/acme/api/pull/7", "repo": "acme/api"}
MINE = dict(REVIEW, kind="mine")


class Recorder:
    def __init__(self, merge_methods=(True, True, False), fail=False):
        self.calls, self.merge_methods, self.fail = [], merge_methods, fail

    def __call__(self, cmd, **kw):
        self.calls.append(cmd)
        if cmd[:2] == ["gh", "api"]:
            return subprocess.CompletedProcess(cmd, 0, json.dumps(list(self.merge_methods)), "")
        return subprocess.CompletedProcess(cmd, 1 if self.fail else 0, "", "boom" if self.fail else "")


def answering(text):
    return lambda prompt, button, kind: text


class RunTest(unittest.TestCase):
    def test_approve_with_and_without_comment(self):
        gh = Recorder()
        self.assertEqual(actions.run("approve", REVIEW, gh, answering("")), (True, "Approved api#7"))
        self.assertEqual(gh.calls[-1], ["gh", "pr", "review", REVIEW["url"], "--approve"])
        actions.run("approve", REVIEW, gh, answering("LGTM"))
        self.assertEqual(gh.calls[-1][-2:], ["--body", "LGTM"])

    def test_request_changes_and_comment(self):
        gh = Recorder()
        actions.run("request-changes", REVIEW, gh, answering("please add tests"))
        self.assertEqual(gh.calls[-1], ["gh", "pr", "review", REVIEW["url"], "--request-changes", "--body",
                                        "please add tests"])
        actions.run("comment", REVIEW, gh, answering("nit"))
        self.assertEqual(gh.calls[-1][:5], ["gh", "pr", "review", REVIEW["url"], "--comment"])
        actions.run("comment", MINE, gh, answering("updated"))
        self.assertEqual(gh.calls[-1], ["gh", "pr", "comment", MINE["url"], "--body", "updated"])

    def test_cancel_runs_nothing(self):
        gh = Recorder()
        self.assertEqual(actions.run("close", MINE, gh, answering(None)), (False, ""))
        self.assertEqual(gh.calls, [])

    def test_merge_uses_the_repo_preference(self):
        gh = Recorder(merge_methods=(True, True, True))
        actions.run("merge", MINE, gh, answering(""))
        self.assertEqual(gh.calls[-1], ["gh", "pr", "merge", MINE["url"], "--squash"])
        gh = Recorder(merge_methods=(False, False, True))
        actions.run("merge", MINE, gh, answering(""))
        self.assertEqual(gh.calls[-1][-1], "--rebase")

    def test_ready_and_draft_need_no_dialog(self):
        gh = Recorder()
        never = lambda *a: self.fail("no dialog expected")
        actions.run("draft", MINE, gh, never)
        self.assertEqual(gh.calls[-1], ["gh", "pr", "ready", MINE["url"], "--undo"])
        actions.run("ready", MINE, gh, never)
        self.assertEqual(gh.calls[-1], ["gh", "pr", "ready", MINE["url"]])

    def test_wrong_kind_and_failures(self):
        with self.assertRaises(actions.ActionError):
            actions.run("merge", REVIEW, Recorder(), answering(""))
        with self.assertRaises(actions.ActionError):
            actions.run("approve", MINE, Recorder(), answering(""))
        with self.assertRaisesRegex(actions.ActionError, "boom"):
            actions.run("close", MINE, Recorder(fail=True), answering(""))


class DialogTest(unittest.TestCase):
    def test_required_text_asks_again_and_cancel_returns_none(self):
        replies = iter(["button returned:Request changes, text returned:", 
                        "button returned:Request changes, text returned:add tests\n"])
        runner = lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, next(replies), "")
        self.assertEqual(actions.ask("Why?", "Request changes", "required", runner), "add tests")
        cancel = lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, "", "User canceled.")
        self.assertIsNone(actions.ask("Sure?", "Close PR", None, cancel))
        quoted = []
        actions.ask('Merge "x"?', "Merge", None,
                    lambda cmd, **kw: quoted.append(cmd[-1]) or subprocess.CompletedProcess(cmd, 0, "button returned:Merge", ""))
        self.assertIn('Merge \\"x\\"?', quoted[0])
