import subprocess
import tempfile
import unittest
from pathlib import Path

from chip import model, tui
from chip.menu import assign_labels


def row(i, repo="acme/shopbox-api", **overrides):
    base = {
        "index": i, "repo": repo, "number": 100 + i, "title": f"feat: thing {i}",
        "url": f"https://github.com/{repo}/pull/{100 + i}", "author": "alice", "wait": "2d",
        "status": model.NEW, "decision": "-", "size": "+1/-0 1f", "ci": "-", "conflict": False,
        "base": "dev", "stacked": False, "jira": "", "draft": False, "stale": False,
    }
    base.update(overrides)
    return base


def inbox(*rows):
    return {"viewer": "me", "rows": assign_labels(list(rows)), "hidden": {"approved": 2, "draft": 0}}


INBOX = inbox(
    row(1, status=model.REREVIEW, wait="1h"),
    row(2, repo="acme/api", jira="MYS-1", conflict=True),
    row(3),
)


def plain(lines):
    return [tui.strip_ansi(line) for line in lines]


class RepoLinesTest(unittest.TestCase):
    def test_all_line_first_then_busiest_repo(self):
        lines = plain(tui.repo_lines(INBOX, picked={2}))
        self.assertTrue(lines[0].startswith("*\t"))
        self.assertIn("Tất cả", lines[0])
        self.assertIn("3 PR", lines[0])
        self.assertIn("☑ 1", lines[0])
        key, text = lines[1].split("\t", 1)
        self.assertEqual(key, "acme/shopbox-api")
        self.assertIn("shopbox-api", text)
        self.assertIn("2 PR", text)
        self.assertIn("1 cần re-review", text)
        self.assertIn("mới nhất 1h", text)
        self.assertEqual(lines[2].split("\t", 1)[0], "acme/api")
        self.assertIn("☑ 1", lines[2])

    def test_repo_preview_lists_titles(self):
        text = tui.strip_ansi(tui.repo_preview(INBOX, "acme/shopbox-api"))
        self.assertIn("#101", text)
        self.assertIn("feat: thing 3", text)
        self.assertNotIn("#102", text)


class PrLinesTest(unittest.TestCase):
    def test_checkbox_and_description(self):
        lines = plain(tui.pr_lines(INBOX, "acme/api", picked={2}))
        self.assertEqual(len(lines), 1)
        index, text = lines[0].split("\t", 1)
        self.assertEqual(index, "2")
        self.assertTrue(text.startswith("☑ #102"))
        for part in ("feat: thing 2", "alice", "2d", "mới", "MYS-1", "conflict"):
            self.assertIn(part, text)

    def test_unpicked_and_all_repos_use_labels(self):
        lines = plain(tui.pr_lines(INBOX, "*", picked=set()))
        self.assertEqual([l.split("\t")[0] for l in lines], ["1", "2", "3"])
        self.assertTrue(lines[0].split("\t", 1)[1].startswith("☐ shopbox-api#101"))

    def test_preview(self):
        text = tui.preview_text(INBOX["rows"][1])
        for part in ("api#102", "https://github.com/acme/api/pull/102", "conflict", "MYS-1"):
            self.assertIn(part, text)


class PickedStateTest(unittest.TestCase):
    def test_toggle_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "picked.json"
            self.assertEqual(tui.load_picked(path), set())
            tui.toggle_picked(path, 3)
            tui.toggle_picked(path, 1)
            self.assertEqual(tui.load_picked(path), {1, 3})
            tui.toggle_picked(path, 3)
            self.assertEqual(tui.load_picked(path), {1})


class RunUiTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name) / "picked.json"
        self.claude_calls, self.asked, self.printed = [], [], []

    def tearDown(self):
        self.tmp.cleanup()

    def fzf(self, script):
        """script: list of (kind, returncode, stdout, indexes_to_toggle) consumed in order."""
        steps = list(script)

        def _fzf(kind, lines, header, repo=None):
            expected_kind, code, stdout, toggles = steps.pop(0)
            assert kind == expected_kind, (kind, expected_kind)
            for i in toggles:
                tui.toggle_picked(self.state, i)
            return subprocess.CompletedProcess([], code, stdout, "")
        return _fzf

    def run_ui(self, script, answers=(), resolve=lambda slug: f"/src/{slug}"):
        answers = list(answers)

        def ask(q):
            self.asked.append(q)
            return answers.pop(0)
        return tui.run_ui(
            INBOX, self.state, fzf=self.fzf(script),
            claude=lambda prompt, cwd: self.claude_calls.append((prompt, cwd)),
            resolve=resolve, clone=lambda slug: f"/clones/{slug}", ask=ask, out=self.printed.append,
        )

    def test_repo_then_ticked_prs_are_reviewed(self):
        self.run_ui([
            ("repos", 0, "acme/shopbox-api\tx\n", []),
            ("prs", 0, "3\tx\n", [1, 3]),
        ], answers=[""])
        self.assertEqual(self.claude_calls, [
            ("/my-review-skill https://github.com/acme/shopbox-api/pull/101", "/src/acme/shopbox-api"),
            ("/my-review-skill https://github.com/acme/shopbox-api/pull/103", "/src/acme/shopbox-api"),
        ])

    def test_enter_without_ticks_reviews_current_line(self):
        self.run_ui([("repos", 0, "*\tx\n", []), ("prs", 0, "2\tx\n", [])])
        self.assertEqual([c[0] for c in self.claude_calls], ["/my-review-skill https://github.com/acme/api/pull/102"])

    def test_escape_in_prs_goes_back_to_repos(self):
        self.run_ui([
            ("repos", 0, "acme/api\tx\n", []),
            ("prs", 130, "", []),
            ("repos", 130, "", []),
        ])
        self.assertEqual(self.claude_calls, [])

    def test_picks_start_empty_each_run(self):
        tui.toggle_picked(self.state, 1)
        self.run_ui([("repos", 130, "", [])])
        self.assertEqual(tui.load_picked(self.state), set())

    def test_stop_between_prs(self):
        self.run_ui([("repos", 0, "*\tx\n", []), ("prs", 0, "1\tx\n", [1, 2])], answers=["n"])
        self.assertEqual(len(self.claude_calls), 1)

    def test_missing_clone_declined_is_skipped(self):
        self.run_ui([("repos", 0, "*\tx\n", []), ("prs", 0, "1\tx\n", [])], answers=["n"],
                    resolve=lambda slug: None)
        self.assertEqual(self.claude_calls, [])
        self.assertTrue(any("Bỏ qua" in p for p in self.printed))

    def test_inbox_zero(self):
        code = tui.run_ui({"rows": [], "hidden": {"approved": 0, "draft": 0}}, self.state,
                          fzf=None, out=self.printed.append)
        self.assertEqual((code, self.printed), (0, ["Inbox zero 🎉"]))
