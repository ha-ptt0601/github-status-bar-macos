import subprocess
import unittest

from chip import fetch


def page(nodes, next_cursor=None):
    return {
        "viewer": {"login": "me"},
        "search": {
            "pageInfo": {"hasNextPage": next_cursor is not None, "endCursor": next_cursor},
            "nodes": nodes,
        },
    }


class FetchTest(unittest.TestCase):
    def test_paginates(self):
        calls = []

        def runner(search, after):
            calls.append(after)
            return page([{"id": "a"}], "c1") if after is None else page([{"id": "b"}])

        viewer, nodes = fetch.search_all("q", runner)
        self.assertEqual(viewer, "me")
        self.assertEqual([n["id"] for n in nodes], ["a", "b"])
        self.assertEqual(calls, [None, "c1"])

    def test_skips_non_pr_nodes(self):
        viewer, nodes = fetch.search_all("q", lambda s, a: page([{}, {"id": "a"}]))
        self.assertEqual([n["id"] for n in nodes], ["a"])

    def test_merges_both_searches_and_dedupes(self):
        responses = {
            fetch.SEARCHES[0]: page([{"id": "a", "src": 1}, {"id": "b"}]),
            fetch.SEARCHES[1]: page([{"id": "a", "src": 2}, {"id": "c"}]),
        }
        viewer, nodes = fetch.fetch_inbox_nodes(lambda s, a: responses[s])
        self.assertEqual(viewer, "me")
        self.assertEqual([n["id"] for n in nodes], ["a", "b", "c"])
        self.assertEqual(nodes[0]["src"], 1)

    def test_searches_exclude_own_prs(self):
        for search in fetch.SEARCHES:
            self.assertIn("-author:@me", search)
            self.assertIn("is:open", search)


class FetchAllTest(unittest.TestCase):
    def test_review_and_mine_searches(self):
        responses = {
            fetch.SEARCHES[0]: page([{"id": "a"}]),
            fetch.SEARCHES[1]: page([{"id": "a"}, {"id": "b"}]),
            fetch.MINE_SEARCH: page([{"id": "m"}]),
        }
        seen = []

        def runner(search, after):
            seen.append(search)
            return responses[search]

        viewer, review_nodes, mine_nodes = fetch.fetch_all(runner)
        self.assertEqual(viewer, "me")
        self.assertEqual([n["id"] for n in review_nodes], ["a", "b"])
        self.assertEqual([n["id"] for n in mine_nodes], ["m"])
        self.assertEqual(sorted(seen), sorted(list(fetch.SEARCHES) + [fetch.MINE_SEARCH]))

    def test_query_asks_for_review_threads(self):
        self.assertIn("reviewThreads(first: 100)", fetch.QUERY)
        self.assertEqual(fetch.MINE_SEARCH, "is:pr is:open author:@me")


class TimeoutRetryTest(unittest.TestCase):
    def test_retries_once_after_a_timeout(self):
        from unittest import mock
        calls = []

        def run(cmd, **kw):
            calls.append(cmd)
            if len(calls) == 1:
                raise subprocess.TimeoutExpired(cmd, kw["timeout"])
            return subprocess.CompletedProcess(cmd, 0, '{"data": {"viewer": {"login": "me"}}}', "")
        with mock.patch("chip.fetch.subprocess.run", run):
            self.assertEqual(fetch.run_gh_graphql("q", None), {"viewer": {"login": "me"}})
        self.assertEqual(len(calls), 2)

    def test_gives_up_after_two_timeouts(self):
        from unittest import mock

        def run(cmd, **kw):
            raise subprocess.TimeoutExpired(cmd, kw["timeout"])
        with mock.patch("chip.fetch.subprocess.run", run):
            with self.assertRaisesRegex(fetch.FetchError, "just woke up"):
                fetch.run_gh_graphql("q", None)
