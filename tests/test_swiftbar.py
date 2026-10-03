import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from chip import fetch, model, swiftbar
from chip.menu import assign_labels
from tests.factory import make_node

PLUGIN = "/p/chip.3m.sh"
CFG = {"skills": [{"name": "Full review", "prompt": "x"}, {"name": "Quick", "prompt": "y"}], "errors": []}


def row(i, repo="acme/api", **kw):
    base = {"index": i, "repo": repo, "number": 2000 + i, "title": f"feat: thing {i}",
            "url": f"https://github.com/{repo}/pull/{2000 + i}", "author": "alice", "wait": "2d",
            "status": model.NEW, "decision": "-", "size": "+57/-7 2f", "ci": "-", "conflict": False,
            "base": "dev", "stacked": False, "jira": "", "draft": False, "stale": False}
    base.update(kw)
    return base


def render(rows, records=None, views=None, **kw):
    inbox = {"rows": assign_labels(rows), "fetched_at": 0}
    return swiftbar.render(inbox, records or {}, views or {}, CFG, PLUGIN, "0.1.0", now=0, **kw)


class HelpersTest(unittest.TestCase):
    def test_sf_config_is_base64_palette_json(self):
        import base64
        decoded = json.loads(base64.b64decode(swiftbar.sf_config("#FF9500")))
        self.assertEqual(decoded, {"renderingMode": "Palette", "colors": ["#FF9500"]})

    def test_escape(self):
        self.assertEqual(swiftbar.esc("a|b"), "a¦b")
        self.assertTrue(swiftbar.esc("-x").startswith("​"))

    def test_item_quotes_values_with_spaces(self):
        self.assertEqual(swiftbar.item("Hi", 1, bash="/a b/c", x="1"), '--Hi | bash="/a b/c" x=1')

    def test_ago_and_details(self):
        self.assertEqual(swiftbar.ago("1d"), "1 day ago")
        self.assertEqual(swiftbar.ago("9h"), "9 hours ago")
        self.assertEqual(swiftbar.details(row(1, stacked=True, base="feature/a", jira="MYS-1", conflict=True)),
                         "+57 −7 · 2 files · base feature/a (stacked) · MYS-1 · conflict")


class RenderTest(unittest.TestCase):
    def test_title_counts_actionable_and_shows_icon(self):
        lines = render([row(1), row(2, status=model.REREVIEW), row(3, status=model.WAITING)])
        self.assertTrue(lines[0].startswith("2 | templateImage="))

    def test_zero_count_title_is_icon_only(self):
        self.assertTrue(render([row(1, status=model.WAITING)])[0].startswith(" | templateImage="))

    def test_project_header_row_and_submenu(self):
        lines = render([row(1), row(2)])
        self.assertIn("API · 2 PRs | size=11 color=#8E8E93", lines)
        pr = next(l for l in lines if l.startswith("#2001"))
        self.assertIn(f"sfimage=sparkle sfconfig={swiftbar.sf_config('#34C759')} font=Menlo size=12", pr)
        self.assertIn("--api#2001 | disabled=true", lines)
        self.assertIn("--New · by alice · opened 2 days ago | disabled=true", lines)
        self.assertIn('--Run "Full review" | sfimage=play.fill bash=/p/chip.3m.sh terminal=false '
                      'param1=run param2=api#2001 param3=--skill param4=1 refresh=true', lines)
        self.assertIn('--Run "Quick" | sfimage=play.fill bash=/p/chip.3m.sh terminal=false '
                      'param1=run param2=api#2001 param3=--skill param4=2 refresh=true', lines)
        self.assertIn("--Open on GitHub | href=https://github.com/acme/api/pull/2001 sfimage=arrow.up.right.square",
                      lines)
        self.assertIn("--Copy link | sfimage=doc.on.doc bash=/p/chip.3m.sh terminal=false param1=copy param2=api#2001",
                      lines)

    def test_projects_ordered_by_actionable_count(self):
        lines = render([row(1, repo="acme/shopbox-api", status=model.WAITING), row(2), row(3)])
        headers = [l for l in lines if "size=11 color=#8E8E93" in l and "·" in l and "PR" in l]
        self.assertEqual([h.split(" ·")[0] for h in headers[:2]], ["API", "SHOPBOX-API"])

    def test_paging_with_nested_next(self):
        lines = render([row(i) for i in range(1, 31)])
        self.assertEqual(len([l for l in lines if l.startswith("#")]), 12)
        self.assertIn("Next 12 ›  (13–24 of 30)", lines)
        self.assertIn("--API (cont.) | size=11 color=#8E8E93", lines)
        self.assertIn("--Next 6 ›  (25–30 of 30)", lines)
        self.assertIn("----API (cont.) | size=11 color=#8E8E93", lines)

    def test_stale_go_to_older_submenu_but_rereview_stays(self):
        lines = render([row(1, stale=True), row(2, stale=True, status=model.REREVIEW), row(3)])
        self.assertIn("Older than 30 days · 1 PR | sfimage=clock color=#8E8E93", lines)
        self.assertTrue(any(l.startswith("#2002") for l in lines))
        self.assertTrue(any(l.startswith("--#2001") for l in lines))

    def test_hidden_rows_in_show_approved_and_drafts(self):
        lines = render([row(1), row(2, status=model.APPROVED), row(3, draft=True)])
        self.assertIn("Show approved & drafts (2) | sfimage=eye.slash", lines)
        self.assertTrue(any(l.startswith("--#2002") and "checkmark.seal" in l for l in lines))

    def test_runs_section_and_row_links(self):
        records = {"api#2001::Full review": {"id": "ab12cd34", "label": "api#2001", "skill": "Full review",
                                             "url": "https://github.com/acme/api/pull/2001", "started_at": 0}}
        views = {"api#2001::Full review": {"kind": "running", "text": "running 3m"}}
        lines = render([row(1)], records, views)
        self.assertIn("Reviews by chip | size=11 color=#8E8E93", lines)
        self.assertIn(f"api#2001 · Full review · running 3m | sfimage=circle.lefthalf.filled "
                      f"sfconfig={swiftbar.sf_config('#0A84FF')}", lines)
        self.assertIn("--View session | sfimage=eye bash=/p/chip.3m.sh terminal=false param1=attach param2=ab12cd34",
                      lines)
        self.assertIn("--Stop | sfimage=stop.circle bash=/p/chip.3m.sh terminal=false param1=stop param2=ab12cd34 "
                      "refresh=true", lines)
        self.assertTrue(any(l.startswith('--Run "Full review" again') for l in lines))
        self.assertTrue(any(l.startswith("--View running review (Full review)") for l in lines))

    def test_error_update_and_config_lines(self):
        cfg_errors = dict(CFG, errors=["skills[1] unknown placeholder(s): pr"])
        lines = swiftbar.render({"rows": [], "fetched_at": 0}, {}, {}, cfg_errors, PLUGIN, "0.1.0",
                                newer="0.2.0", error="HTTP 401", now=0)
        self.assertTrue(lines[0].startswith("! | templateImage="))
        self.assertTrue(any(l.startswith("Update available: v0.2.0 — Update now") for l in lines))
        self.assertTrue(any(l.startswith("Could not refresh: HTTP 401") for l in lines))
        self.assertTrue(any(l.startswith("Config: skills[1] unknown placeholder") for l in lines))
        self.assertTrue(any(l.startswith("Nothing waiting for your review") for l in lines))

    def test_no_inbox_still_offers_refresh_and_settings(self):
        lines = swiftbar.render(None, {}, {}, CFG, PLUGIN, "0.1.0", error="offline", now=0)
        self.assertFalse(any(l.startswith("Pull requests ·") for l in lines))
        self.assertTrue(any(l.startswith("Refresh now") for l in lines))
        self.assertIn("--About chip v0.1.0 | disabled=true", lines)


class BuildMenuTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = os.environ.get("CHIP_CACHE_DIR")
        os.environ["CHIP_CACHE_DIR"] = self.tmp.name
        self.nodes = [make_node(id="a", number=1)]
        self.calls = []

    def tearDown(self):
        if self.old is None:
            os.environ.pop("CHIP_CACHE_DIR", None)
        else:
            os.environ["CHIP_CACHE_DIR"] = self.old
        self.tmp.cleanup()

    def fetch_runner(self, search, after):
        nodes = self.nodes if search == fetch.SEARCHES[0] else []
        return {"viewer": {"login": "me"}, "search": {"pageInfo": {"hasNextPage": False, "endCursor": None},
                                                       "nodes": nodes}}

    def runner(self, cmd, **kw):
        self.calls.append(cmd)
        if cmd[:2] == ["gh", "api"]:
            return subprocess.CompletedProcess(cmd, 1, "", "Not Found")
        return subprocess.CompletedProcess(cmd, 0, "[]", "")

    def test_first_cycle_silent_then_notifies_new_pr(self):
        out = swiftbar.build_menu(PLUGIN, fetch_runner=self.fetch_runner, runner=self.runner, now=1000)
        self.assertTrue(out.startswith("1 | templateImage="))
        self.assertFalse(any(c[0] == "osascript" for c in self.calls))
        self.assertTrue(Path(self.tmp.name, "notify.json").exists())
        self.nodes.append(make_node(id="b", number=2, url="https://github.com/acme/api/pull/2"))
        swiftbar.build_menu(PLUGIN, force=True, fetch_runner=self.fetch_runner, runner=self.runner, now=2000)
        notes = [c for c in self.calls if c[0] == "osascript"]
        self.assertEqual(len(notes), 1)
        self.assertIn("New review request: api#2", notes[0][2])
