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
CFG = {"skills": [{"name": "Full review", "prompt": "x"}, {"name": "Quick", "prompt": "y"}], "errors": [],
       "status_style": "symbols"}


def row(i, repo="acme/api", **kw):
    base = {"index": i, "repo": repo, "number": 2000 + i, "title": f"feat: thing {i}",
            "url": f"https://github.com/{repo}/pull/{2000 + i}", "author": "alice", "wait": "2d",
            "status": model.NEW, "decision": "-", "size": "+57/-7 2f", "ci": "-", "conflict": False,
            "base": "dev", "stacked": False, "jira": "", "draft": False, "stale": False}
    base.update(kw)
    return base


def render(rows, records=None, views=None, style="symbols", **kw):
    inbox = {"rows": assign_labels(rows), "fetched_at": 0}
    cfg = dict(CFG, status_style=style)
    return swiftbar.render(inbox, records or {}, views or {}, cfg, PLUGIN, "0.1.0", now=0, **kw)


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
        self.assertIn("API · 2 PRs | size=11 color=#8E8E93 proj=api", lines)
        pr = next(l for l in lines if l.startswith("#2001"))
        self.assertIn(f"sfimage=sparkle sfconfig={swiftbar.sf_config('#34C759')} tooltip=New font=Menlo size=12", pr)
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

    def test_every_project_visible_with_capped_rows(self):
        rows = [row(i) for i in range(1, 16)] + [row(20, repo="acme/mailer-api"), row(21, repo="acme/mailer-api")]
        lines = render(rows)
        top = [l for l in lines if l.startswith("#")]
        self.assertEqual(len(top), 7)  # 5 from API + 2 from mailer-api
        self.assertIn("API · 15 PRs | size=11 color=#8E8E93 proj=api", lines)
        self.assertIn("MAILER-API · 2 PRs | size=11 color=#8E8E93 proj=mailer-api", lines)
        self.assertIn("10 more in API › | color=#8E8E93 proj=api", lines)
        self.assertFalse(any(l.startswith("Next ") for l in lines))

    def test_more_submenu_pages_with_nested_next(self):
        lines = render([row(i) for i in range(1, 31)])
        self.assertIn("25 more in API › | color=#8E8E93 proj=api", lines)
        self.assertEqual(len([l for l in lines if l.startswith("--#")]), 12)
        self.assertIn("--Next 12 ›  (13–24 of 25)", lines)
        self.assertIn("----Next 1 ›  (25–25 of 25)", lines)

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
        self.assertFalse(any(l.startswith('--Run "Full review"') for l in lines))
        self.assertTrue(any(l.startswith("--View running review") for l in lines))

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


class StatusStyleTest(unittest.TestCase):
    def rows(self):
        return [row(1, status=model.REREVIEW), row(2), row(3, status=model.COMMENTED)]

    def pr_line(self, lines, number):
        return next(l for l in lines if f"#{number}" in l.split(" | ")[0] and not l.startswith("-"))

    def test_dots_show_colored_dot_and_label(self):
        lines = render(self.rows(), style="dots")
        line = self.pr_line(lines, 2001)
        self.assertTrue(line.startswith("🟠 #2001  Re-review  feat: thing 1"))
        self.assertNotIn("sfimage", line)
        self.assertIn("tooltip=Re-review", line)
        self.assertTrue(self.pr_line(lines, 2002).startswith("🟢 #2002  New"))
        self.assertTrue(self.pr_line(lines, 2003).startswith("⚪ #2003  Commented"))

    def test_emoji_rows_and_legend(self):
        lines = render(self.rows(), style="emoji")
        self.assertTrue(self.pr_line(lines, 2001).startswith("🔁 #2001  feat: thing 1"))
        self.assertTrue(self.pr_line(lines, 2002).startswith("🆕 #2002"))
        self.assertIn("🔁 Re-review · 🆕 New · 💬 Commented · ⏳ Waiting on author | size=11 color=#8E8E93", lines)

    def test_symbols_keep_sf_images_with_tooltip(self):
        line = self.pr_line(render(self.rows(), style="symbols"), 2001)
        self.assertIn("sfimage=arrow.triangle.2.circlepath", line)
        self.assertIn("tooltip=Re-review", line)

    def test_runs_use_dots_outside_symbols_style(self):
        records = {"api#2001::Full review": {"id": "ab", "label": "api#2001", "skill": "Full review",
                                             "url": "u", "started_at": 0}}
        views = {"api#2001::Full review": {"kind": "running", "text": "running 3m"}}
        lines = render([row(1)], records, views, style="dots")
        self.assertIn("🔵 api#2001 · Full review · running 3m", lines)

    def test_settings_offer_styles_with_checkmark(self):
        lines = render(self.rows(), style="emoji")
        self.assertIn("--Status style | sfimage=paintpalette", lines)
        self.assertIn("----Colored dots + label | keep=radio bash=/p/chip.3m.sh terminal=false param1=config param2=set "
                      "param3=status_style param4=dots refresh=true", lines)
        self.assertIn("----Emoji | keep=radio checked=true bash=/p/chip.3m.sh terminal=false param1=config param2=set "
                      "param3=status_style param4=emoji refresh=true", lines)
        self.assertIn("----Symbols | keep=radio bash=/p/chip.3m.sh terminal=false param1=config param2=set "
                      "param3=status_style param4=symbols refresh=true", lines)


class RunOnRowTest(unittest.TestCase):
    KEY = "api#2001::Full review"

    def lines(self, kind, text, style="dots", started=0):
        records = {self.KEY: {"id": "ab", "label": "api#2001", "skill": "Full review", "url": "u", "started_at": started}}
        views = {self.KEY: {"kind": kind, "text": text}}
        return render([row(1), row(2)], records, views, style=style)

    def pr_line(self, lines, number):
        return next(l for l in lines if f"#{number}" in l.split(" | ")[0] and not l.startswith("-"))

    def test_running_review_replaces_status_on_the_row(self):
        line = self.pr_line(self.lines("running", "running 3m"), 2001)
        self.assertTrue(line.startswith("🔵 #2001  Reviewing  feat: thing 1"))
        self.assertIn('tooltip="Full review · running 3m"', line)
        self.assertTrue(self.pr_line(self.lines("running", "running 3m"), 2002).startswith("🟢 #2002  New"))

    def test_needs_you_and_done(self):
        self.assertTrue(self.pr_line(self.lines("needs_you", "needs you"), 2001).startswith("🟡 #2001  Needs you"))
        self.assertTrue(self.pr_line(self.lines("done", "done 11:40"), 2001).startswith("✅ #2001  Reviewed"))

    def test_gone_run_keeps_pr_status(self):
        self.assertTrue(self.pr_line(self.lines("gone", "session gone"), 2001).startswith("🟢 #2001  New"))

    def test_emoji_and_symbols_styles(self):
        self.assertTrue(self.pr_line(self.lines("running", "running 3m", "emoji"), 2001).startswith("🔵 #2001  feat"))
        self.assertIn("sfimage=circle.lefthalf.filled", self.pr_line(self.lines("running", "running 3m", "symbols"), 2001))

    def test_title_counts_active_reviews(self):
        self.assertTrue(self.lines("running", "running 3m")[0].startswith("2 🔵1 | templateImage="))
        self.assertTrue(self.lines("needs_you", "needs you")[0].startswith("2 🟡1 | templateImage="))
        self.assertTrue(self.lines("done", "done 11:40")[0].startswith("2 | templateImage="))


class RoundMenuTest(unittest.TestCase):
    KEY = "api#2001::Full review"

    def lines(self, kind, resolved=False, round_no=1):
        rec = {"id": "ab12cd34", "session_id": "ab12cd34-full", "label": "api#2001", "skill": "Full review",
               "url": "u", "started_at": 0, "round": round_no, "done_at": 0}
        if resolved:
            rec.update(resolved_at=1, resolved_by="new commits")
        views = {self.KEY: {"kind": kind, "text": {"done": "done 07:00", "running": "running 3m"}.get(kind, kind)}}
        return render([row(1)], {self.KEY: rec}, views, style="dots")

    def test_resolved_round_leaves_reviews_section_and_row(self):
        lines = self.lines("done", resolved=True)
        self.assertNotIn("Reviews by chip | size=11 color=#8E8E93", lines)
        self.assertTrue(next(l for l in lines if l.startswith("🟢 #2001")).startswith("🟢 #2001  New"))

    def test_submenu_remembers_last_round_and_continues(self):
        lines = self.lines("done", resolved=True)
        self.assertIn("--Last chip review · Full review · round 1 · 07:00 · resolved (new commits) | disabled=true",
                      [l.replace(datetime_hm(0), "07:00") for l in lines])
        self.assertIn("--Continue review (round 2) | sfimage=play.fill bash=/p/chip.3m.sh terminal=false "
                      "param1=run param2=api#2001 param3=--skill param4=1 refresh=true", lines)
        self.assertIn("--Open last session | sfimage=eye bash=/p/chip.3m.sh terminal=false param1=attach "
                      "param2=ab12cd34", lines)
        self.assertFalse(any(l.startswith('--Run "Full review"') for l in lines))
        self.assertTrue(any(l.startswith('--Run "Quick"') for l in lines))

    def test_unresolved_round_still_in_reviews_section(self):
        lines = self.lines("done")
        self.assertIn("Reviews by chip | size=11 color=#8E8E93", lines)
        self.assertTrue(any(l.startswith("✅ #2001  Reviewed") for l in lines))

    def test_running_round_offers_view_not_continue(self):
        lines = self.lines("running", round_no=2)
        self.assertTrue(any(l.startswith("--Last chip review · Full review · round 2 · running 3m") for l in lines))
        self.assertTrue(any(l.startswith("--View running review") for l in lines))
        self.assertFalse(any(l.startswith("--Continue review") for l in lines))


def datetime_hm(ts):
    from datetime import datetime
    return datetime.fromtimestamp(ts).strftime("%H:%M")


class MineSectionTest(unittest.TestCase):
    CFG = dict(CFG, status_style="dots", address_skills=[{"name": "Address review", "prompt": "a {url}"}],
               hidden_projects=[])

    def mine(self, number, status, reviewers=None, requested=None, unresolved=0, title="fix(auth): single-use TOTP"):
        r = row(number - 2000, title=title)
        r.update(number=number, url=f"https://github.com/acme/api/pull/{number}", kind="mine",
                 mine_status=status, reviewers=reviewers or {}, requested=requested or [], unresolved=unresolved)
        return r

    def render(self, mine, rows=None, view="mine", cfg=None, query="", records=None, views=None):
        inbox = {"rows": assign_labels(rows if rows is not None else [row(1)]), "mine": assign_labels(mine),
                 "fetched_at": 0}
        return swiftbar.render(inbox, records or {}, views or {}, cfg or self.CFG, PLUGIN, "0.1.0", now=0,
                               view=view, query=query)

    def line(self, lines, number):
        return next(l for l in lines if f"#{number}" in l.split(" | ")[0] and not l.startswith("-"))

    def test_one_icon_with_tabs(self):
        mine = [self.mine(2119, model.CHANGES, {"bob": "CHANGES_REQUESTED"})]
        review = self.render(mine, view="review")
        self.assertTrue(review[0].startswith("1 🔴1 | templateImage="))
        self.assertIn("Review requests · 1 | tab=review checked=true bash=/p/chip.3m.sh terminal=false param1=view "
                      "param2=review refresh=true", review)
        self.assertIn("My pull requests · 1 · 🔴1 | tab=mine bash=/p/chip.3m.sh terminal=false param1=view "
                      "param2=mine refresh=true", review)
        self.assertFalse(any(l.startswith("🔴 #2119") for l in review))
        own = self.render(mine)
        self.assertTrue(own[0].startswith("1 🔴1 | templateImage="))
        self.assertIn("My pull requests · 1 · 🔴1 | tab=mine checked=true bash=/p/chip.3m.sh terminal=false param1=view "
                      "param2=mine refresh=true", own)
        self.assertTrue(any(l.startswith("🔴 #2119") for l in own))
        self.assertFalse(any(l.startswith("🟢 #2001") for l in own))

    def test_rows_show_status_and_reviewers(self):
        lines = self.render([
            self.mine(2119, model.CHANGES, {"bob": "CHANGES_REQUESTED", "carol": "APPROVED"}),
            self.mine(2116, model.THREADS, {"carol": "COMMENTED"}, unresolved=3),
            self.mine(2122, model.AWAITING, requested=["bob", "carol"]),
        ])
        self.assertTrue(self.line(lines, 2119).startswith("🔴 #2119  Changes    fix(auth): single-use TOTP"))
        self.assertIn("bob ✗ carol ✓ |", self.line(lines, 2119))
        self.assertTrue(self.line(lines, 2116).startswith("💬 #2116  3 threads  "))
        self.assertIn("→ bob, carol |", self.line(lines, 2122))

    def test_submenu_actions(self):
        lines = self.render([self.mine(2119, model.CHANGES, {"bob": "CHANGES_REQUESTED", "carol": "APPROVED"})])
        self.assertIn("--Changes requested · opened 2 days ago | disabled=true", lines)
        self.assertIn("--Reviews: bob ✗ · carol ✓ | disabled=true", lines)
        self.assertIn('--Run "Address review" | sfimage=play.fill bash=/p/chip.3m.sh terminal=false param1=run '
                      'param2=api#2119 param3=--skill param4=1 param5=--address refresh=true', lines)
        self.assertIn("--Re-request review (bob) | sfimage=bell bash=/p/chip.3m.sh terminal=false param1=nudge "
                      "param2=api#2119 refresh=true", lines)

    def test_no_rerequest_when_everyone_approved(self):
        lines = self.render([self.mine(2118, model.READY, {"carol": "APPROVED"})])
        self.assertFalse(any(l.startswith("--Re-request review") for l in lines))

    def test_search_and_projects_controls(self):
        lines = self.render([self.mine(2119, model.CHANGES)], view="review")
        self.assertIn("Search… | sfimage=magnifyingglass bash=/p/chip.3m.sh terminal=false param1=search "
                      "refresh=true", lines)
        self.assertIn("Projects | sfimage=square.grid.2x2", lines)
        self.assertIn("--Show all | keep=all bash=/p/chip.3m.sh terminal=false param1=project param2=all refresh=true", lines)
        self.assertIn("--api | keep=toggle checked=true bash=/p/chip.3m.sh terminal=false param1=project param2=toggle "
                      "param3=api refresh=true", lines)

    def test_hidden_project_is_unchecked_and_filtered(self):
        cfg = dict(self.CFG, hidden_projects=["api"])
        lines = self.render([], rows=[row(1), row(2, repo="acme/mailer-api")], view="review", cfg=cfg)
        # Hidden projects stay listed but tagged, so GitHubBar can show them in place.
        hidden = [l for l in lines if "#2001" in l.split(" | ")[0] and not l.startswith("-")]
        self.assertTrue(hidden and all("proj=api hidden=true" in l for l in hidden))
        self.assertTrue(any("#2002" in l.split(" | ")[0] for l in lines if not l.startswith("-")))
        self.assertIn("--api | keep=toggle bash=/p/chip.3m.sh terminal=false param1=project param2=toggle param3=api "
                      "refresh=true", lines)

    def test_query_filters_and_offers_clear(self):
        lines = self.render([], rows=[row(1), row(2, title="update(newsletter): migrate")], view="review",
                            query="newsletter")
        tops = [l for l in lines if not l.startswith("-") and "#200" in l.split(" | ")[0]]
        self.assertEqual(len(tops), 1)
        self.assertIn('"newsletter" · 1 match — Clear search | sfimage=xmark.circle bash=/p/chip.3m.sh '
                      'terminal=false param1=search param2=--clear refresh=true', lines)

    def test_runs_split_by_view(self):
        recs = {"api#2001::Full review": {"id": "r1", "label": "api#2001", "skill": "Full review", "url": "u",
                                          "started_at": 0, "kind": "review"},
                "api#2119::Address review": {"id": "a1", "label": "api#2119", "skill": "Address review",
                                             "url": "u", "started_at": 0, "kind": "address"}}
        views = {k: {"kind": "running", "text": "running 1m"} for k in recs}
        mine = [self.mine(2119, model.THREADS, unresolved=1)]
        review = self.render(mine, view="review", records=recs, views=views)
        own = self.render(mine, view="mine", records=recs, views=views)
        self.assertTrue(any(l.startswith("🔵 api#2001") for l in review))
        self.assertFalse(any(l.startswith("🔵 api#2119") for l in review))
        self.assertTrue(any(l.startswith("🔵 api#2119") for l in own))
        self.assertTrue(own[0].startswith("1 🔵2 | templateImage="))


class RecentNotificationsTest(unittest.TestCase):
    def test_section_links_prs_and_sessions(self):
        history = [{"text": "Review finished: api#1 (Full review)", "run": "ab", "at": 0},
                   {"text": "New review request: api#2 — t", "href": "https://x/2", "at": 0}]
        lines = render([row(1)], history=history)
        start = lines.index(swiftbar.item("Recent notifications", 0, sfimage="bell"))
        self.assertIn("param1=attach param2=ab", lines[start + 1])
        self.assertIn("href=https://x/2", lines[start + 2])
        self.assertIn("param1=notifications param2=--clear", lines[start + 4])

    def test_no_history_no_section(self):
        self.assertFalse(any("Recent notifications" in line for line in render([row(1)])))

    def test_deliver_lines_sit_in_the_title_block(self):
        lines = render([row(1)], deliver=[{"text": "chip v9 is available", "href": "https://r"}])
        self.assertEqual(lines[2], "---")
        self.assertEqual(lines[1], 'chip v9 is available | notify=true href=https://r')


class LiveSearchTest(unittest.TestCase):
    def test_field_body_tags_and_search_rows(self):
        lines = render([row(1), row(2, title='say "hi" | bye')], live_search=True)
        self.assertIn("Search pull requests | searchfield=true", lines)
        self.assertFalse(any(l.startswith("Search…") for l in lines))
        header = next(l for l in lines if l.startswith("API · 2 PRs"))
        self.assertTrue(header.endswith("proj=api body=true"))
        found = [l for l in lines if "searchonly=true" in l]
        self.assertEqual(len(found), 2)
        self.assertIn('find="api#2002 acme/api say hi bye alice"', found[1])
        self.assertIn("No matching pull requests | color=#8E8E93 nomatch=true", lines)

    def test_off_by_default(self):
        lines = render([row(1)])
        self.assertTrue(any(l.startswith("Search…") for l in lines))
        self.assertFalse(any("searchonly" in l or "body=true" in l for l in lines))


class PanesTest(unittest.TestCase):
    def test_both_tabs_follow_one_title_block(self):
        review = ["title", "notice | notify=true", "---", "Review requests", "r1"]
        mine = ["title", "---", "My pull requests", "m1"]
        self.assertEqual(swiftbar.both_panes(review, mine, "mine"), [
            "title", "notice | notify=true", "---",
            " | pane=review", "Review requests", "r1",
            " | pane=mine active=true", "My pull requests", "m1"])


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

    def test_events_are_remembered_and_queued_for_githubbar(self):
        env = {"GITHUBBAR_NOTIFY": "1"}
        swiftbar.build_menu(PLUGIN, fetch_runner=self.fetch_runner, runner=self.runner, now=1000, env=env)
        self.nodes.append(make_node(id="b", number=2, url="https://github.com/acme/api/pull/2"))
        out = swiftbar.build_menu(PLUGIN, force=True, fetch_runner=self.fetch_runner, runner=self.runner,
                                  now=2000, env=env)
        self.assertFalse(any(c[0] == "osascript" for c in self.calls))
        self.assertNotIn("notify=true", out.split("\n---\n")[0])  # queued, not delivered yet
        self.assertIn("Recent notifications", out)
        self.assertIn("href=https://github.com/acme/api/pull/2", out)
        delivered = swiftbar.build_menu(PLUGIN, fetch_runner=self.fetch_runner, runner=self.runner,
                                        now=2010, env=env, deliver=True)
        title_block = delivered.split("\n---\n")[0].splitlines()
        self.assertEqual(len(title_block), 2)
        self.assertIn("New review request: api#2", title_block[1])
        self.assertIn("notify=true", title_block[1])
        again = swiftbar.build_menu(PLUGIN, fetch_runner=self.fetch_runner, runner=self.runner,
                                    now=2020, env=env, deliver=True)
        self.assertEqual(len(again.split("\n---\n")[0].splitlines()), 1)  # the outbox was drained

    def test_round_resolves_when_commits_land_after_it(self):
        Path(self.tmp.name, "runs.json").write_text(json.dumps({"api#1::Full review": {
            "id": "ab", "label": "api#1", "skill": "Full review", "url": "u", "started_at": 0, "done_at": 10}}))
        swiftbar.build_menu(PLUGIN, fetch_runner=self.fetch_runner, runner=self.runner, now=1000)
        record = json.loads(Path(self.tmp.name, "runs.json").read_text())["api#1::Full review"]
        self.assertEqual(record["resolved_by"], "new commits")
