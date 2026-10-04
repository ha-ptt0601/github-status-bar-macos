import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from chip import cli, config, fetch, runs, store
from tests.factory import make_node


def fake_runner(search, after):
    nodes = [make_node(id="a", number=274)] if search == fetch.SEARCHES[0] else []
    return {
        "viewer": {"login": "me"},
        "search": {"pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": nodes},
    }


def failing_runner(search, after):
    raise fetch.FetchError("HTTP 401: Bad credentials")


class CliCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = {k: os.environ.get(k) for k in ("CHIP_CACHE_DIR", "CHIP_WORK_ROOT")}
        os.environ["CHIP_CACHE_DIR"] = str(Path(self.tmp.name) / "cache")
        os.environ["CHIP_WORK_ROOT"] = str(Path(self.tmp.name) / "work")

    def tearDown(self):
        for key, value in self.env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def run_cli(self, argv, runner=None):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(argv, runner=runner)
        return code, out.getvalue(), err.getvalue()


class CliTest(CliCase):
    def test_list_prints_table_and_saves_rows(self):
        code, out, _ = self.run_cli(["list"], runner=fake_runner)
        self.assertEqual(code, 0)
        self.assertIn("| 1 | api | #274 |", out)
        saved = json.loads((Path(os.environ["CHIP_CACHE_DIR"]) / "last.json").read_text())
        self.assertEqual(saved["rows"][0]["number"], 274)

    def test_list_auth_error(self):
        code, _, err = self.run_cli(["list"], runner=failing_runner)
        self.assertEqual(code, 1)
        self.assertIn("gh auth login", err)

    def test_pick(self):
        self.run_cli(["list"], runner=fake_runner)
        code, out, _ = self.run_cli(["pick", "1"])
        self.assertEqual(code, 0)
        picked = json.loads(out)
        self.assertEqual(picked, [{
            "index": 1, "label": "api#274", "repo": "acme/api", "number": 274,
            "title": "feat: thing", "url": "https://github.com/acme/api/pull/1",
        }])

    def test_pick_bad_selection(self):
        self.run_cli(["list"], runner=fake_runner)
        code, _, err = self.run_cli(["pick", "9"])
        self.assertEqual(code, 2)
        self.assertIn("'9'", err)

    def test_pick_without_list(self):
        code, _, err = self.run_cli(["pick", "1"])
        self.assertEqual(code, 2)
        self.assertIn("chip menu", err)

    def test_repo_missing(self):
        code, _, err = self.run_cli(["repo", "acme/nope"])
        self.assertEqual(code, 2)
        self.assertIn("acme/nope", err)


class MenuCliTest(CliCase):
    def test_menu_first_page_fetches_and_labels(self):
        code, out, _ = self.run_cli(["menu"], runner=fake_runner)
        self.assertEqual(code, 0)
        page = json.loads(out)
        self.assertEqual((page["page"], page["pages"], page["total"]), (1, 1, 1))
        self.assertEqual(page["hidden"], {"approved": 0, "draft": 0})
        self.assertEqual(page["questions"][0]["options"][0]["label"], "api#274")

    def test_menu_next_page_reads_cache_without_fetch(self):
        self.run_cli(["menu"], runner=fake_runner)
        code, out, _ = self.run_cli(["menu", "--page", "1"], runner=failing_runner)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["page"], 1)

    def test_menu_page_out_of_range(self):
        self.run_cli(["menu"], runner=fake_runner)
        code, _, err = self.run_cli(["menu", "--page", "5"])
        self.assertEqual(code, 2)
        self.assertIn("page 5", err)

    def test_menu_inbox_zero(self):
        empty = lambda s, a: {"viewer": {"login": "me"},
                              "search": {"pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": []}}
        code, out, _ = self.run_cli(["menu"], runner=empty)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["total"], 0)

    def test_pick_by_label(self):
        self.run_cli(["menu"], runner=fake_runner)
        code, out, _ = self.run_cli(["pick", "api#274"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)[0]["label"], "api#274")


class FilterCliTest(CliCase):
    def runner(self, search, after):
        nodes = [
            make_node(id="a", number=1, title="update(newsletter): migrate"),
            make_node(id="b", number=2, title="fix(orders)", repository={
                "nameWithOwner": "acme/shopbox-api", "defaultBranchRef": {"name": "master"}}),
        ] if search == fetch.SEARCHES[0] else []
        return {"viewer": {"login": "me"},
                "search": {"pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": nodes}}

    def labels(self, page):
        return [o["label"] for q in page["questions"] if q["multiSelect"] for o in q["options"]]

    def test_query_on_first_fetch(self):
        code, out, _ = self.run_cli(["menu", "--q", "newsletter"], runner=self.runner)
        page = json.loads(out)
        self.assertEqual((code, page["total"], page["filter"]), (0, 1, "q=newsletter"))
        self.assertEqual(self.labels(page), ["api#1", "None"])

    def test_repo_filter_from_cache(self):
        self.run_cli(["menu"], runner=self.runner)
        code, out, _ = self.run_cli(["menu", "--cached", "--repo", "shopbox-api"], runner=failing_runner)
        page = json.loads(out)
        self.assertEqual((code, page["total"], page["filter"]), (0, 1, "repo=shopbox-api"))
        self.assertEqual(self.labels(page)[0], "shopbox-api#2")

    def test_filter_without_match(self):
        self.run_cli(["menu"], runner=self.runner)
        code, out, _ = self.run_cli(["menu", "--cached", "--q", "nothing-here"])
        self.assertEqual((code, json.loads(out)["total"]), (0, 0))

    def test_pick_label_outside_current_filter(self):
        self.run_cli(["menu", "--q", "newsletter"], runner=self.runner)
        code, out, _ = self.run_cli(["pick", "shopbox-api#2"])
        self.assertEqual((code, json.loads(out)[0]["number"]), (0, 2))

    def test_repos_questions(self):
        self.run_cli(["menu"], runner=self.runner)
        code, out, _ = self.run_cli(["repos"])
        options = json.loads(out)["questions"][0]["options"]
        self.assertEqual((code, [o["label"] for o in options]), (0, ["All", "api", "shopbox-api"]))

    def test_repos_refresh_fetches_first(self):
        code, out, _ = self.run_cli(["repos", "--refresh"], runner=self.runner)
        data = json.loads(out)
        self.assertEqual((code, data["total"], data["hidden"]), (0, 2, {"approved": 0, "draft": 0}))
        self.assertEqual(data["questions"][0]["options"][0]["label"], "All")


class PreviewCliTest(CliCase):
    def test_preview_from_cache(self):
        self.run_cli(["menu"], runner=fake_runner)
        code, out, _ = self.run_cli(["preview", "1"])
        self.assertEqual(code, 0)
        self.assertIn("api#274", out)
        self.assertIn("https://github.com/acme/api/pull/1", out)

    def test_preview_bad_index(self):
        self.run_cli(["menu"], runner=fake_runner)
        code, _, _ = self.run_cli(["preview", "9"])
        self.assertEqual(code, 2)

    def test_no_subcommand_opens_ui(self):
        seen = {}
        original = cli.tui.run_ui
        cli.tui.run_ui = lambda inbox, state, **kw: seen.setdefault("rows", len(inbox["rows"])) and 0
        try:
            code, _, _ = self.run_cli([], runner=fake_runner)
        finally:
            cli.tui.run_ui = original
        self.assertEqual((code, seen["rows"]), (0, 1))


class OpenCliTest(CliCase):
    def test_open_runs_osascript_for_apple_terminal(self):
        calls = []
        original = cli.subprocess.run
        cli.subprocess.run = lambda cmd, **kw: calls.append(cmd) or cli.subprocess.CompletedProcess(cmd, 0, "", "")
        term = os.environ.get("TERM_PROGRAM")
        os.environ["TERM_PROGRAM"] = "Apple_Terminal"
        try:
            code, out, _ = self.run_cli(["open"])
        finally:
            cli.subprocess.run = original
            if term is None:
                os.environ.pop("TERM_PROGRAM", None)
            else:
                os.environ["TERM_PROGRAM"] = term
        self.assertEqual(code, 0)
        self.assertEqual(calls[0][:2], ["osascript", "-e"])
        self.assertIn('tell application "Terminal"', calls[0][2])
        self.assertIn("bin/chip", calls[0][2])


class PickerCallbacksTest(CliCase):
    def test_toggle_then_prs_shows_tick(self):
        self.run_cli(["menu"], runner=fake_runner)
        self.run_cli(["_toggle", "1"])
        code, out, _ = self.run_cli(["_prs", "acme/api"])
        self.assertEqual(code, 0)
        self.assertIn("☑", out)
        self.run_cli(["_toggle", "1"])
        _, out, _ = self.run_cli(["_prs", "*"])
        self.assertIn("☐", out)

    def test_repo_preview(self):
        self.run_cli(["menu"], runner=fake_runner)
        code, out, _ = self.run_cli(["_repo-preview", "acme/api"])
        self.assertEqual(code, 0)
        self.assertIn("#274", out)


class CacheTtlTest(CliCase):
    def test_refresh_reuses_recent_fetch(self):
        self.run_cli(["repos", "--refresh"], runner=fake_runner)
        code, out, _ = self.run_cli(["repos", "--refresh"], runner=failing_runner)
        self.assertEqual(code, 0)
        self.assertIn("fetched_at", json.loads(out))

    def test_force_bypasses_cache(self):
        self.run_cli(["repos", "--refresh"], runner=fake_runner)
        code, _, _ = self.run_cli(["repos", "--refresh", "--force"], runner=failing_runner)
        self.assertEqual(code, 1)

    def test_stale_cache_refetches(self):
        self.run_cli(["repos", "--refresh"], runner=fake_runner)
        last = Path(os.environ["CHIP_CACHE_DIR"]) / "last.json"
        data = json.loads(last.read_text())
        data["fetched_at"] -= cli.CACHE_TTL_SECONDS + 1
        last.write_text(json.dumps(data))
        code, _, _ = self.run_cli(["repos", "--refresh"], runner=failing_runner)
        self.assertEqual(code, 1)

    def test_all_flag_reuses_cache(self):
        self.run_cli(["repos", "--refresh"], runner=fake_runner)
        code, _, _ = self.run_cli(["repos", "--refresh", "--all"], runner=failing_runner)
        self.assertEqual(code, 0)


class MentionPickTest(CliCase):
    def test_pick_accepts_resource_mentions(self):
        self.run_cli(["menu"], runner=fake_runner)
        code, out, _ = self.run_cli(["pick", "review @chip:pr://api/274-feat-thing please"])
        self.assertEqual((code, json.loads(out)[0]["label"]), (0, "api#274"))


class ConfigCliTest(CliCase):
    def setUp(self):
        super().setUp()
        self.cfg_old = os.environ["CHIP_CONFIG"]
        os.environ["CHIP_CONFIG"] = str(Path(self.tmp.name) / "config.json")

    def tearDown(self):
        os.environ["CHIP_CONFIG"] = self.cfg_old
        super().tearDown()

    def test_check_ok_then_bad(self):
        code, out, _ = self.run_cli(["config", "check"])
        self.assertEqual(code, 0)
        self.assertIn("Address review", out)
        Path(os.environ["CHIP_CONFIG"]).write_text(json.dumps({"skills": [{"name": "A", "prompt": "/a {pr}"}]}))
        code, _, err = self.run_cli(["config", "check"])
        self.assertEqual(code, 1)
        self.assertIn("unknown placeholder", err)

    def test_init_and_path(self):
        code, out, _ = self.run_cli(["config", "init"])
        self.assertEqual(code, 0)
        self.assertTrue(Path(os.environ["CHIP_CONFIG"]).exists())
        _, out, _ = self.run_cli(["config", "path"])
        self.assertEqual(out.strip(), os.environ["CHIP_CONFIG"])

    def test_prompt_for_label(self):
        self.run_cli(["menu"], runner=fake_runner)
        code, out, _ = self.run_cli(["prompt", "api#274"])
        self.assertEqual((code, out.strip()), (0, config.REVIEW_PROMPT.format(url="https://github.com/acme/api/pull/1")))

    def test_prompt_unknown(self):
        self.run_cli(["menu"], runner=fake_runner)
        code, _, _ = self.run_cli(["prompt", "nope#1"])
        self.assertEqual(code, 2)


class RunCliBase(CliCase):
    def setUp(self):
        super().setUp()
        self.calls = []
        self.orig_run, self.orig_resolve = cli.subprocess.run, cli.repos.resolve
        cli.subprocess.run = self.fake
        cli.repos.resolve = lambda slug, roots, cache, clone_root=None: "/src/" + slug

    def tearDown(self):
        cli.subprocess.run, cli.repos.resolve = self.orig_run, self.orig_resolve
        super().tearDown()

    def fake(self, cmd, **kw):
        self.calls.append(cmd)
        out = "backgrounded · ab12cd34 · x\n" if cmd[:1] == ["claude"] and "--bg" in cmd else ""
        return subprocess.CompletedProcess(cmd, 0, out, "")

    def runs_path(self):
        return Path(os.environ["CHIP_CACHE_DIR"]) / "runs.json"

    def start(self):
        self.run_cli(["menu"], runner=fake_runner)
        return self.run_cli(["run", "api#274"])



class RunCliTest(RunCliBase):
    def test_run_starts_background_review_and_notifies(self):
        code, out, _ = self.start()
        self.assertEqual(code, 0)
        bg = next(c for c in self.calls if "--bg" in c)
        self.assertTrue(bg[1].startswith(config.REVIEW_PROMPT.format(url="https://github.com/acme/api/pull/1")))
        self.assertIn("git worktree with pull request #274 checked out", bg[1])
        worktree = str(Path(os.environ["CHIP_CACHE_DIR"]) / "worktrees" / "api-274")
        self.assertIn(["git", "-C", "/src/acme/api", "worktree", "add", "--quiet", "--detach", worktree,
                       "refs/chip/pr-274"], self.calls)
        self.assertEqual(runs.load(self.runs_path())["api#274::Review"]["cwd"], worktree)
        self.assertTrue(any(c[0] == "osascript" for c in self.calls))
        self.assertIn("ab12cd34", out)
        self.assertIn("api#274::Review", runs.load(self.runs_path()))

    def test_run_project_uses_repo_skill_in_a_worktree(self):
        with tempfile.TemporaryDirectory() as tmp:
            clone = Path(tmp) / "api"
            (clone / ".claude" / "skills" / "review").mkdir(parents=True)
            (clone / ".claude" / "skills" / "review" / "SKILL.md").write_text("x")
            cli.repos.resolve = lambda slug, roots, cache, clone_root=None: str(clone)
            os.environ["CHIP_WORK_ROOT"] = tmp
            try:
                self.run_cli(["menu"], runner=fake_runner)
                code, out, _ = self.run_cli(["run", "api#274", "--project"])
            finally:
                os.environ.pop("CHIP_WORK_ROOT")
            self.assertEqual(code, 0)
            worktree = str(Path(os.environ["CHIP_CACHE_DIR"]) / "worktrees" / "api-274")
            self.assertTrue(any(c[:5] == ["git", "-C", str(clone), "worktree", "add"] for c in self.calls))
            bg = next(c for c in self.calls if "--bg" in c)
            self.assertTrue(bg[1].startswith("/review https://github.com/acme/api/pull/1\n"))
            record = runs.load(self.runs_path())["api#274::/review (project)"]
            self.assertEqual((record["cwd"], record["worktree"], record["clone"], record["auto"]),
                             (worktree, worktree, str(clone), True))

    def test_run_project_without_repo_skill_falls_back_to_builtin(self):
        self.run_cli(["menu"], runner=fake_runner)
        code, _, _ = self.run_cli(["run", "api#274", "--project"])
        self.assertEqual(code, 0)
        record = runs.load(self.runs_path())["api#274::Review"]  # built-in review, still in the PR worktree
        self.assertEqual((record["cwd"], record["clone"], record["auto"]),
                         (str(Path(os.environ["CHIP_CACHE_DIR"]) / "worktrees" / "api-274"), "/src/acme/api", True))

    def test_run_clones_an_unknown_repo_and_says_so(self):
        cli.repos.resolve = lambda slug, roots, cache, clone_root=None: None
        cloned = Path(os.environ["CHIP_CACHE_DIR"]) / "repos" / "api"
        orig_clone = cli.repos.clone
        cli.repos.clone = lambda slug, root, cache: str(cloned)
        try:
            self.run_cli(["menu"], runner=fake_runner)
            code, _, _ = self.run_cli(["run", "api#274"])
        finally:
            cli.repos.clone = orig_clone
        self.assertEqual(code, 0)
        notes = [c[2] for c in self.calls if c[0] == "osascript"]
        self.assertIn("Cloning acme/api", notes[0])
        self.assertIn("without .claude/settings.local.json, .env, vendor, node_modules", notes[1])
        self.assertIn("Reviewing api#274", notes[2])

    def test_run_reports_a_failed_clone(self):
        cli.repos.resolve = lambda slug, roots, cache, clone_root=None: None
        orig_clone = cli.repos.clone

        def fail(slug, root, cache):
            raise cli.repos.CloneError("repository not found")
        cli.repos.clone = fail
        try:
            self.run_cli(["menu"], runner=fake_runner)
            code, _, err = self.run_cli(["run", "api#274"])
        finally:
            cli.repos.clone = orig_clone
        self.assertEqual(code, 1)
        self.assertIn("could not clone acme/api (do you have access?", err)

    def test_run_unknown_label(self):
        self.run_cli(["menu"], runner=fake_runner)
        code, _, _ = self.run_cli(["run", "nope#1"], runner=fake_runner)
        self.assertEqual(code, 1)

    def test_run_bad_skill_number(self):
        self.run_cli(["menu"], runner=fake_runner)
        code, _, _ = self.run_cli(["run", "api#274", "--skill", "5"])
        self.assertEqual(code, 2)

    def test_stop_forget_attach_copy(self):
        self.start()
        self.run_cli(["stop", "ab12cd34"])
        self.assertIn(["claude", "stop", "ab12cd34"], self.calls)
        self.run_cli(["attach", "ab12cd34"])
        self.assertTrue(any(c[0] == "osascript" and "claude attach ab12cd34" in c[2] for c in self.calls))
        self.run_cli(["copy", "api#274"])
        self.assertIn(["pbcopy"], self.calls)
        self.run_cli(["forget", "ab12cd34"])
        self.assertIn(["claude", "rm", "ab12cd34"], self.calls)
        self.assertTrue(any(c[3:5] == ["worktree", "remove"] for c in self.calls))  # nothing else uses it
        self.assertEqual(runs.load(self.runs_path()), {})

    def test_attach_falls_back_to_resume_when_background_session_is_gone(self):
        self.start()
        records = runs.load(self.runs_path())
        records["api#274::Review"]["session_id"] = "ab12cd34-full"
        runs.save(self.runs_path(), records)
        self.calls.clear()
        self.run_cli(["attach", "ab12cd34"])
        script = next(c[2] for c in self.calls if c[0] == "osascript")
        self.assertIn("claude --resume ab12cd34-full", script)
        self.assertIn(f"cd {Path(os.environ['CHIP_CACHE_DIR']) / 'worktrees' / 'api-274'}", script)

    def test_unknown_run_id(self):
        code, _, _ = self.run_cli(["stop", "zzzz"])
        self.assertEqual(code, 2)


class ConfigSetCliTest(CliCase):
    def setUp(self):
        super().setUp()
        self.cfg_old = os.environ["CHIP_CONFIG"]
        os.environ["CHIP_CONFIG"] = str(Path(self.tmp.name) / "config.json")

    def tearDown(self):
        os.environ["CHIP_CONFIG"] = self.cfg_old
        super().tearDown()

    def test_set_status_style(self):
        code, _, _ = self.run_cli(["config", "set", "status_style", "emoji"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(Path(os.environ["CHIP_CONFIG"]).read_text())["status_style"], "emoji")

    def test_set_rejects_bad_value(self):
        code, _, err = self.run_cli(["config", "set", "status_style", "stars"])
        self.assertEqual(code, 2)
        self.assertIn("status_style must be one of", err)

    def test_set_needs_key_and_value(self):
        code, _, err = self.run_cli(["config", "set", "status_style"])
        self.assertEqual(code, 2)


class MinePrCliTest(RunCliBase):
    def mine_runner(self, search, after):
        nodes = []
        if search == fetch.MINE_SEARCH:
            nodes = [make_node(id="m", number=119, url="https://github.com/acme/api/pull/119",
                               author={"login": "me"},
                               latestReviews={"nodes": [
                                   {"author": {"login": "bob"}, "state": "CHANGES_REQUESTED", "submittedAt": "2026-10-01T00:00:00Z"},
                                   {"author": {"login": "carol"}, "state": "APPROVED", "submittedAt": "2026-10-01T00:00:00Z"},
                                   {"author": {"login": "chiennv"}, "state": "COMMENTED", "submittedAt": "2026-10-01T00:00:00Z"}]})]
        return {"viewer": {"login": "me"},
                "search": {"pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": nodes}}

    def test_address_run_uses_address_skill(self):
        self.run_cli(["menu"], runner=self.mine_runner)
        code, _, _ = self.run_cli(["run", "api#119", "--address"])
        self.assertEqual(code, 0)
        bg = next(c for c in self.calls if "--bg" in c)
        self.assertTrue(bg[1].startswith("Help me address the review feedback on my pull request "
                                         "https://github.com/acme/api/pull/119"))
        self.assertIn("Bash(git push:*)", bg[bg.index("--disallowedTools") + 1])

    def test_nudge_rerequests_reviewers_who_did_not_approve(self):
        self.run_cli(["menu"], runner=self.mine_runner)
        code, _, _ = self.run_cli(["nudge", "api#119"])
        self.assertEqual(code, 0)
        self.assertIn(["gh", "api", "-X", "POST", "repos/acme/api/pulls/119/requested_reviewers",
                       "-f", "reviewers[]=bob", "-f", "reviewers[]=chiennv"], self.calls)

    def test_nudge_unknown_label(self):
        self.run_cli(["menu"], runner=self.mine_runner)
        code, _, _ = self.run_cli(["nudge", "api#1"])
        self.assertEqual(code, 2)


class SearchProjectCliTest(RunCliBase):
    def setUp(self):
        super().setUp()
        self.cfg_old = os.environ["CHIP_CONFIG"]
        os.environ["CHIP_CONFIG"] = str(Path(self.tmp.name) / "config.json")
        self.dialog = "button returned:Search, text returned:omni send"

    def tearDown(self):
        os.environ["CHIP_CONFIG"] = self.cfg_old
        super().tearDown()

    def fake(self, cmd, **kw):
        self.calls.append(cmd)
        if cmd[:2] == ["osascript", "-e"] and "display dialog" in cmd[2]:
            if self.dialog is None:
                return subprocess.CompletedProcess(cmd, 1, "", "User canceled. (-128)")
            return subprocess.CompletedProcess(cmd, 0, self.dialog + "\n", "")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    def test_search_dialog_saves_query(self):
        code, _, _ = self.run_cli(["search"])
        self.assertEqual(code, 0)
        self.assertEqual(store.load_query(), "omni send")
        self.assertIn('default answer ""', next(c[2] for c in self.calls if "display dialog" in c[2]))

    def test_cancel_keeps_query_and_clear_button_clears(self):
        store.save_query("old")
        self.dialog = None
        self.run_cli(["search"])
        self.assertEqual(store.load_query(), "old")
        self.dialog = "button returned:Clear, text returned:old"
        self.run_cli(["search"])
        self.assertEqual(store.load_query(), "")

    def test_search_clear_flag(self):
        store.save_query("x")
        self.run_cli(["search", "--clear"])
        self.assertEqual(store.load_query(), "")

    def test_project_toggle_and_all(self):
        self.run_cli(["project", "toggle", "loyalty-partners"])
        self.assertEqual(config.load()["hidden_projects"], ["loyalty-partners"])
        self.run_cli(["project", "all"])
        self.assertEqual(config.load()["hidden_projects"], [])

    def test_view_switch_is_remembered(self):
        self.assertEqual(store.load_view(), "review")
        self.run_cli(["view", "mine"])
        self.assertEqual(store.load_view(), "mine")
        self.run_cli(["view", "review"])
        self.assertEqual(store.load_view(), "review")
