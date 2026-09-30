import subprocess
import unittest

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


class LinesTest(unittest.TestCase):
    def test_line_starts_with_hidden_index_and_shows_columns(self):
        line = tui.fzf_lines(inbox(row(1, jira="MYS-1")))[0]
        index, visible = line.split("\t", 1)
        self.assertEqual(index, "1")
        plain = tui.strip_ansi(visible)
        for part in ("shopbox-api#101", "2d", "mới", "feat: thing 1", "alice", "MYS-1"):
            self.assertIn(part, plain)

    def test_preview(self):
        text = tui.preview_text(assign_labels([row(1, stacked=True, base="feature/a", conflict=True, jira="MYS-1",
                                                   decision="CHANGES_REQ 1✗", status=model.REREVIEW)])[0])
        self.assertIn("shopbox-api#101", text)
        self.assertIn("https://github.com/acme/shopbox-api/pull/101", text)
        self.assertIn("feature/a (stacked)", text)
        self.assertIn("conflict", text)
        self.assertIn("cần re-review", text)

    def test_selected_indexes(self):
        output = "3\tshopbox-api#103 …\n1\tshopbox-api#101 …\n"
        self.assertEqual(tui.selected_indexes(output), [3, 1])


class RunUiTest(unittest.TestCase):
    def setUp(self):
        self.claude_calls, self.asked, self.printed = [], [], []

    def fzf(self, output, code=0):
        return lambda lines, header: subprocess.CompletedProcess([], code, output, "")

    def claude(self, prompt, cwd):
        self.claude_calls.append((prompt, cwd))

    def ask(self, answers):
        answers = list(answers)

        def _ask(question):
            self.asked.append(question)
            return answers.pop(0)
        return _ask

    def run_ui(self, fzf, answers=(), resolve=lambda slug: f"/src/{slug}", clone=None):
        return tui.run_ui(
            inbox(row(1), row(2, repo="acme/api")),
            fzf=fzf, claude=self.claude, resolve=resolve,
            clone=clone or (lambda slug: f"/clones/{slug}"),
            ask=self.ask(answers), out=self.printed.append,
        )

    def test_reviews_each_pick_in_its_repo_and_asks_between(self):
        code = self.run_ui(self.fzf("1\tx\n2\ty\n"), answers=[""])
        self.assertEqual(code, 0)
        self.assertEqual(self.claude_calls, [
            ("/my-review-skill https://github.com/acme/shopbox-api/pull/101", "/src/acme/shopbox-api"),
            ("/my-review-skill https://github.com/acme/api/pull/102", "/src/acme/api"),
        ])
        self.assertEqual(len(self.asked), 1)
        self.assertIn("api#102", self.asked[0])

    def test_stop_between_prs(self):
        self.run_ui(self.fzf("1\tx\n2\ty\n"), answers=["n"])
        self.assertEqual(len(self.claude_calls), 1)

    def test_escape_does_nothing(self):
        code = self.run_ui(self.fzf("", code=130))
        self.assertEqual((code, self.claude_calls), (0, []))

    def test_missing_clone_declined_is_skipped(self):
        self.run_ui(self.fzf("1\tx\n"), answers=["n"], resolve=lambda slug: None)
        self.assertEqual(self.claude_calls, [])
        self.assertTrue(any("Bỏ qua" in p for p in self.printed))

    def test_missing_clone_accepted_is_cloned(self):
        self.run_ui(self.fzf("1\tx\n"), answers=["y"], resolve=lambda slug: None)
        self.assertEqual(self.claude_calls[0][1], "/clones/acme/shopbox-api")
