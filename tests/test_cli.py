import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from chip import cli, fetch
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
        self.assertIn("trang 5", err)

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
        self.assertEqual(self.labels(page), ["api#1", "Không chọn"])

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
        self.assertEqual((code, [o["label"] for o in options]), (0, ["Tất cả", "api", "shopbox-api"]))

    def test_repos_refresh_fetches_first(self):
        code, out, _ = self.run_cli(["repos", "--refresh"], runner=self.runner)
        data = json.loads(out)
        self.assertEqual((code, data["total"], data["hidden"]), (0, 2, {"approved": 0, "draft": 0}))
        self.assertEqual(data["questions"][0]["options"][0]["label"], "Tất cả")


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
