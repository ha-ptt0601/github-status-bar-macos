import json
import os
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

from chip import fetch, model, store
from tests.factory import make_node, review

NODES = [
    make_node(id="a", number=1),
    make_node(id="b", number=2, isDraft=True),
    make_node(id="c", number=3, latestReviews={"nodes": [review("me", "APPROVED", "2026-09-29T05:00:00Z")]}),
]


def page(nodes):
    return {"viewer": {"login": "me"},
            "search": {"pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": nodes}}


MINE = [make_node(id="m", number=7, author={"login": "me"})]


def runner(search, after):
    if search == fetch.MINE_SEARCH:
        return page(MINE)
    return page(NODES if search == fetch.SEARCHES[0] else [])


def failing(search, after):
    raise fetch.FetchError("HTTP 401: Bad credentials")


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = os.environ.get("CHIP_CACHE_DIR")
        os.environ["CHIP_CACHE_DIR"] = self.tmp.name

    def tearDown(self):
        if self.old is None:
            os.environ.pop("CHIP_CACHE_DIR", None)
        else:
            os.environ["CHIP_CACHE_DIR"] = self.old
        self.tmp.cleanup()

    def test_load_all_keeps_hidden_rows_and_labels(self):
        inbox, error = store.load_all(runner)
        self.assertIsNone(error)
        self.assertEqual(sorted(r["number"] for r in inbox["rows"]), [1, 2, 3])
        self.assertTrue(all("label" in r for r in inbox["rows"]))
        self.assertTrue(inbox["all_rows"])

    def test_load_all_keeps_my_prs_labelled(self):
        inbox, _ = store.load_all(runner)
        self.assertEqual([(r["number"], r["label"], r["kind"]) for r in inbox["mine"]], [(7, "api#7", "mine")])

    def test_reuses_recent_fetch(self):
        store.load_all(runner)
        inbox, error = store.load_all(failing)
        self.assertIsNone(error)
        self.assertEqual(len(inbox["rows"]), 3)

    def test_force_refetch_error_returns_stale_cache(self):
        store.load_all(runner)
        inbox, error = store.load_all(failing, force=True)
        self.assertIn("401", error)
        self.assertEqual(len(inbox["rows"]), 3)

    def test_old_filtered_cache_is_ignored(self):
        Path(self.tmp.name, "last.json").write_text(json.dumps({"rows": [], "fetched_at": time.time()}))
        inbox, _ = store.load_all(runner)
        self.assertEqual(len(inbox["rows"]), 3)

    def test_cached_all_none_without_cache(self):
        self.assertIsNone(store.cached_all())


class VisibleViewTest(unittest.TestCase):
    def setUp(self):
        self.inbox = model.build_inbox(NODES, "me", datetime(2026, 9, 30, tzinfo=timezone.utc), show_all=True)

    def test_hides_drafts_and_approved_and_reindexes(self):
        view = model.visible_view(self.inbox)
        self.assertEqual([r["number"] for r in view["rows"]], [1])
        self.assertEqual(view["rows"][0]["index"], 1)
        self.assertEqual(view["hidden"], {"approved": 1, "draft": 1})

    def test_show_all_keeps_everything(self):
        view = model.visible_view(self.inbox, show_all=True)
        self.assertEqual(len(view["rows"]), 3)
        self.assertEqual(view["hidden"], {"approved": 0, "draft": 0})

    def test_does_not_mutate_input(self):
        model.visible_view(self.inbox)
        self.assertEqual(len(self.inbox["rows"]), 3)
