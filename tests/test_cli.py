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
