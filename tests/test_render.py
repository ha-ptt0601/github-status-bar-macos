import unittest

from chip import model
from chip.render import render_table


def row(**overrides):
    base = {
        "index": 1, "repo": "acme/shopbox-api", "number": 274, "title": "fix: a | b",
        "url": "u", "author": "alice", "wait": "6h", "status": model.REREVIEW,
        "decision": "REQUIRED", "size": "+1/-0 1f", "ci": "✓", "conflict": False,
        "base": "dev", "stacked": False, "jira": "", "draft": False,
    }
    base.update(overrides)
    return base


class RenderTableTest(unittest.TestCase):
    def test_table_row(self):
        out = render_table({"rows": [row()], "hidden": {"approved": 0, "draft": 0}})
        lines = out.splitlines()
        self.assertTrue(lines[0].startswith("| # | Repo | PR | Title |"))
        self.assertIn("| 1 | shopbox-api | #274 | fix: a \\| b | alice | 6h | Re-review |", lines[2])
        self.assertIn("| ok | dev | - |", lines[2])
        self.assertNotIn("Hidden:", out)

    def test_stacked_conflict_jira(self):
        out = render_table({"rows": [row(stacked=True, base="feature/a", conflict=True, jira="MYS-1")],
                            "hidden": {"approved": 0, "draft": 0}})
        self.assertIn("| conflict | feature/a (stacked) | MYS-1 |", out)

    def test_long_title_truncated(self):
        out = render_table({"rows": [row(title="x" * 80)], "hidden": {"approved": 0, "draft": 0}})
        self.assertIn("x" * 49 + "…", out)

    def test_inbox_zero_with_hidden_footer(self):
        out = render_table({"rows": [], "hidden": {"approved": 2, "draft": 1}})
        self.assertIn("Inbox zero 🎉", out)
        self.assertIn("Hidden: 2 approved, 1 drafts", out)
