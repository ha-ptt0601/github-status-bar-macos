"""Builders for raw GraphQL PullRequest nodes used across tests."""


def review(login, state, submitted_at):
    return {"author": {"login": login}, "state": state, "submittedAt": submitted_at}


def commits_at(committed_date, ci="SUCCESS"):
    rollup = {"state": ci} if ci else None
    return {"nodes": [{"commit": {"committedDate": committed_date, "statusCheckRollup": rollup}}]}


def make_node(**overrides):
    node = {
        "id": "PR_1",
        "number": 1,
        "title": "feat: thing",
        "url": "https://github.com/acme/api/pull/1",
        "isDraft": False,
        "createdAt": "2026-09-29T00:00:00Z",
        "author": {"login": "alice"},
        "repository": {"nameWithOwner": "acme/api", "defaultBranchRef": {"name": "master"}},
        "baseRefName": "dev",
        "headRefName": "feature/x",
        "additions": 10,
        "deletions": 2,
        "changedFiles": 3,
        "mergeable": "MERGEABLE",
        "reviewDecision": "REVIEW_REQUIRED",
        "commits": commits_at("2026-09-29T00:00:00Z"),
        "latestReviews": {"nodes": []},
        "reviewRequests": {"nodes": []},
    }
    node.update(overrides)
    return node
