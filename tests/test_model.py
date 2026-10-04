import unittest
from datetime import datetime, timezone

from chip import model
from tests.factory import commits_at, make_node, review

NOW = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)
MINE_AT = "2026-09-29T05:00:00Z"


def reviews(*items):
    return {"nodes": list(items)}


class MyStatusTest(unittest.TestCase):
    def test_no_review_is_new(self):
        self.assertEqual(model.my_status(make_node(), "me"), model.NEW)

    def test_other_reviewers_do_not_count(self):
        node = make_node(latestReviews=reviews(review("bob", "APPROVED", MINE_AT)))
        self.assertEqual(model.my_status(node, "me"), model.NEW)

    def test_pending_review_is_ignored(self):
        node = make_node(latestReviews=reviews(review("me", "PENDING", None)))
        self.assertEqual(model.my_status(node, "me"), model.NEW)

    def test_approved(self):
        node = make_node(latestReviews=reviews(review("me", "APPROVED", MINE_AT)))
        self.assertEqual(model.my_status(node, "me"), model.APPROVED)

    def test_changes_requested_waits_for_author(self):
        node = make_node(latestReviews=reviews(review("me", "CHANGES_REQUESTED", MINE_AT)))
        self.assertEqual(model.my_status(node, "me"), model.WAITING)

    def test_commented(self):
        node = make_node(latestReviews=reviews(review("me", "COMMENTED", MINE_AT)))
        self.assertEqual(model.my_status(node, "me"), model.COMMENTED)

    def test_commit_after_my_review_needs_rereview(self):
        node = make_node(
            commits=commits_at("2026-09-30T01:00:00Z"),
            latestReviews=reviews(review("me", "CHANGES_REQUESTED", MINE_AT)),
        )
        self.assertEqual(model.my_status(node, "me"), model.REREVIEW)

    def test_explicit_rerequest_needs_rereview(self):
        node = make_node(
            latestReviews=reviews(review("me", "APPROVED", MINE_AT)),
            reviewRequests={"nodes": [{"requestedReviewer": {"login": "me"}}]},
        )
        self.assertEqual(model.my_status(node, "me"), model.REREVIEW)


class ColumnsTest(unittest.TestCase):
    def row(self, **overrides):
        return model.build_row(make_node(**overrides), "me", NOW)

    def test_format_wait(self):
        self.assertEqual(model.format_wait("2026-09-30T11:15:00Z", NOW), "45m")
        self.assertEqual(model.format_wait("2026-09-30T06:00:00Z", NOW), "6h")
        self.assertEqual(model.format_wait("2026-09-21T12:00:00Z", NOW), "9d")

    def test_ci(self):
        self.assertEqual(self.row(commits=commits_at(MINE_AT, "SUCCESS"))["ci"], "✓")
        self.assertEqual(self.row(commits=commits_at(MINE_AT, "FAILURE"))["ci"], "✗")
        self.assertEqual(self.row(commits=commits_at(MINE_AT, "PENDING"))["ci"], "…")
        self.assertEqual(self.row(commits=commits_at(MINE_AT, None))["ci"], "-")

    def test_stacked(self):
        self.assertFalse(self.row(baseRefName="dev")["stacked"])
        self.assertFalse(self.row(baseRefName="master")["stacked"])
        self.assertTrue(self.row(baseRefName="feature/a")["stacked"])

    def test_jira_from_title_then_branch(self):
        self.assertEqual(self.row(title="MYS-12 fix")["jira"], "MYS-12")
        self.assertEqual(self.row(headRefName="feature/MYS-303-order")["jira"], "MYS-303")
        self.assertEqual(self.row()["jira"], "")

    def test_decision(self):
        row = self.row(
            reviewDecision="CHANGES_REQUESTED",
            latestReviews=reviews(review("bob", "APPROVED", MINE_AT), review("eve", "CHANGES_REQUESTED", MINE_AT)),
        )
        self.assertEqual(row["decision"], "CHANGES_REQ 1✓ 1✗")
        self.assertEqual(self.row(reviewDecision=None)["decision"], "-")

    def test_size_and_conflict(self):
        row = self.row(mergeable="CONFLICTING")
        self.assertEqual(row["size"], "+10/-2 3f")
        self.assertTrue(row["conflict"])


class InboxTest(unittest.TestCase):
    def nodes(self):
        return [
            make_node(id="a", number=1, createdAt="2026-09-20T00:00:00Z"),
            make_node(id="b", number=2, createdAt="2026-09-10T00:00:00Z"),
            make_node(id="c", number=3, latestReviews=reviews(review("me", "CHANGES_REQUESTED", MINE_AT))),
            make_node(
                id="d", number=4,
                commits=commits_at("2026-09-30T01:00:00Z"),
                latestReviews=reviews(review("me", "COMMENTED", MINE_AT)),
            ),
            make_node(id="e", number=5, latestReviews=reviews(review("me", "APPROVED", MINE_AT))),
            make_node(id="f", number=6, isDraft=True),
        ]

    def test_hides_approved_and_drafts(self):
        inbox = model.build_inbox(self.nodes(), "me", NOW)
        self.assertEqual([r["number"] for r in inbox["rows"]], [4, 2, 1, 3])
        self.assertEqual([r["index"] for r in inbox["rows"]], [1, 2, 3, 4])
        self.assertEqual(inbox["hidden"], {"approved": 1, "draft": 1})
        self.assertEqual(inbox["viewer"], "me")

    def test_show_all(self):
        inbox = model.build_inbox(self.nodes(), "me", NOW, show_all=True)
        self.assertEqual(len(inbox["rows"]), 6)
        self.assertEqual(inbox["hidden"], {"approved": 0, "draft": 0})


class StaleOrderTest(unittest.TestCase):
    def test_stale_prs_go_last_but_rereview_stays_first(self):
        nodes = [
            make_node(id="old-new", number=1, createdAt="2026-05-01T00:00:00Z"),
            make_node(id="fresh", number=2, createdAt="2026-09-29T00:00:00Z"),
            make_node(id="old-waiting", number=3, createdAt="2026-06-01T00:00:00Z",
                      latestReviews=reviews(review("me", "CHANGES_REQUESTED", MINE_AT))),
            make_node(id="fresh-waiting", number=4, createdAt="2026-09-20T00:00:00Z",
                      latestReviews=reviews(review("me", "CHANGES_REQUESTED", MINE_AT))),
            make_node(id="old-rereview", number=5, createdAt="2026-04-01T00:00:00Z",
                      commits=commits_at("2026-09-30T01:00:00Z"),
                      latestReviews=reviews(review("me", "COMMENTED", MINE_AT))),
        ]
        inbox = model.build_inbox(nodes, "me", NOW)
        self.assertEqual([r["number"] for r in inbox["rows"]], [5, 2, 4, 1, 3])
        self.assertEqual([r["stale"] for r in inbox["rows"]], [True, False, False, True, True])


class ReviewTimesTest(unittest.TestCase):
    def test_last_commit_and_my_latest_review(self):
        node = make_node(commits=commits_at("2026-09-30T01:00:00Z"),
                         latestReviews=reviews(review("me", "COMMENTED", MINE_AT),
                                               review("bob", "APPROVED", "2026-09-30T02:00:00Z")))
        row = model.build_row(node, "me", NOW)
        self.assertEqual(row["last_commit_at"], "2026-09-30T01:00:00Z")
        self.assertEqual(row["my_review_at"], MINE_AT)

    def test_no_review(self):
        self.assertIsNone(model.build_row(make_node(), "me", NOW)["my_review_at"])
