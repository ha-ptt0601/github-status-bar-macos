"""Turn raw GraphQL PullRequest nodes into inbox rows."""
from __future__ import annotations

import re
from datetime import datetime
from typing import List, Optional

NEW = "new"
REREVIEW = "re-review"
WAITING = "waiting-author"
COMMENTED = "commented"
APPROVED = "approved"

# Status of the viewer's own PRs, in display priority.
CHANGES = "changes"
CI_FAILED = "ci-failed"
CONFLICT = "conflict"
THREADS = "threads"
READY = "ready"
AWAITING = "awaiting-review"
DRAFT = "draft"
MINE_ORDER = [CHANGES, CI_FAILED, CONFLICT, THREADS, READY, AWAITING, DRAFT]

STATUS_GROUP = {REREVIEW: 0, NEW: 1, WAITING: 2, COMMENTED: 2, APPROVED: 4}
STALE_GROUP = 3
STALE_DAYS = 30
TRUNK_BRANCHES = {"dev", "develop", "main", "master"}
JIRA_RE = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")
CI_MAP = {"SUCCESS": "✓", "FAILURE": "✗", "ERROR": "✗", "PENDING": "…", "EXPECTED": "…"}
DECISION_MAP = {"APPROVED": "APPROVED", "CHANGES_REQUESTED": "CHANGES_REQ", "REVIEW_REQUIRED": "REQUIRED"}


def parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def format_wait(created_at: str, now: datetime) -> str:
    seconds = max(0, int((now - parse_ts(created_at)).total_seconds()))
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h"
    return f"{seconds // 86400}d"


def _nodes(node: dict, key: str) -> List[dict]:
    return (node.get(key) or {}).get("nodes") or []


def _login(obj: Optional[dict]) -> Optional[str]:
    return (obj or {}).get("login")


def _last_commit(node: dict) -> dict:
    commits = _nodes(node, "commits")
    return (commits[-1].get("commit") or {}) if commits else {}


def _my_review_at(node: dict, viewer: str) -> Optional[str]:
    times = [r["submittedAt"] for r in _nodes(node, "latestReviews")
             if _login(r.get("author")) == viewer and r.get("submittedAt")]
    return max(times, key=parse_ts) if times else None


def my_status(node: dict, viewer: str) -> str:
    mine = [
        r for r in _nodes(node, "latestReviews")
        if _login(r.get("author")) == viewer and r.get("submittedAt")
    ]
    if not mine:
        return NEW
    latest = max(mine, key=lambda r: parse_ts(r["submittedAt"]))
    re_requested = any(_login(r.get("requestedReviewer")) == viewer for r in _nodes(node, "reviewRequests"))
    committed = _last_commit(node).get("committedDate")
    if re_requested or (committed and parse_ts(committed) > parse_ts(latest["submittedAt"])):
        return REREVIEW
    if latest["state"] == "APPROVED":
        return APPROVED
    if latest["state"] == "CHANGES_REQUESTED":
        return WAITING
    return COMMENTED


def decision(node: dict) -> str:
    label = DECISION_MAP.get(node.get("reviewDecision") or "", "-")
    states = [r.get("state") for r in _nodes(node, "latestReviews")]
    approved, changes = states.count("APPROVED"), states.count("CHANGES_REQUESTED")
    if approved:
        label += f" {approved}✓"
    if changes:
        label += f" {changes}✗"
    return label


def build_row(node: dict, viewer: str, now: datetime) -> dict:
    repo = node["repository"]
    default_branch = (repo.get("defaultBranchRef") or {}).get("name")
    base = node.get("baseRefName") or ""
    rollup = _last_commit(node).get("statusCheckRollup") or {}
    jira = JIRA_RE.search(node.get("title") or "") or JIRA_RE.search(node.get("headRefName") or "")
    return {
        "repo": repo["nameWithOwner"],
        "language": (repo.get("primaryLanguage") or {}).get("name") or "",
        "number": node["number"],
        "title": node.get("title") or "",
        "url": node["url"],
        "author": _login(node.get("author")) or "ghost",
        "created_at": node["createdAt"],
        "wait": format_wait(node["createdAt"], now),
        "stale": (now - parse_ts(node["createdAt"])).days > STALE_DAYS,
        "status": my_status(node, viewer),
        "decision": decision(node),
        "size": f"+{node.get('additions', 0)}/-{node.get('deletions', 0)} {node.get('changedFiles', 0)}f",
        "ci": CI_MAP.get(rollup.get("state") or "", "-"),
        "conflict": node.get("mergeable") == "CONFLICTING",
        "base": base,
        "stacked": base != default_branch and base not in TRUNK_BRANCHES,
        "jira": jira.group(0) if jira else "",
        "draft": bool(node.get("isDraft")),
        "last_commit_at": _last_commit(node).get("committedDate"),
        "my_review_at": _my_review_at(node, viewer),
    }


def _group(row: dict) -> int:
    """Re-review always first; other PRs older than STALE_DAYS sink below the fresh ones."""
    group = STATUS_GROUP[row["status"]]
    if row["stale"] and group in (STATUS_GROUP[NEW], STATUS_GROUP[WAITING]):
        return STALE_GROUP
    return group


def build_inbox(nodes: List[dict], viewer: str, now: datetime, show_all: bool = False) -> dict:
    hidden = {"approved": 0, "draft": 0}
    rows = []
    for row in (build_row(n, viewer, now) for n in nodes):
        if not show_all and row["draft"]:
            hidden["draft"] += 1
        elif not show_all and row["status"] == APPROVED:
            hidden["approved"] += 1
        else:
            rows.append(row)
    rows.sort(key=lambda r: (_group(r), r["created_at"]))
    for index, row in enumerate(rows, 1):
        row["index"] = index
    return {"viewer": viewer, "rows": rows, "hidden": hidden}


def visible_view(inbox_all: dict, show_all: bool = False) -> dict:
    """A copy of an all-rows inbox with drafts and approved PRs hidden (unless show_all), re-indexed."""
    hidden = {"approved": 0, "draft": 0}
    rows = []
    for row in inbox_all["rows"]:
        if not show_all and row["draft"]:
            hidden["draft"] += 1
        elif not show_all and row["status"] == APPROVED:
            hidden["approved"] += 1
        else:
            rows.append(dict(row))
    for index, row in enumerate(rows, 1):
        row["index"] = index
    view = dict(inbox_all)
    view.update(rows=rows, hidden=hidden)
    return view


def _mine_status(row: dict) -> str:
    states = set(row["reviewers"].values())
    if row["draft"]:
        return DRAFT
    if "CHANGES_REQUESTED" in states:
        return CHANGES
    if row["ci"] == CI_MAP["FAILURE"]:
        return CI_FAILED
    if row["conflict"]:
        return CONFLICT
    if row["unresolved"]:
        return THREADS
    if "APPROVED" in states:
        return READY
    return AWAITING


def build_mine_row(node: dict, viewer: str, now: datetime) -> dict:
    """A row for one of the viewer's own PRs: who reviewed it, who is requested, open threads, status."""
    row = build_row(node, viewer, now)
    row["kind"] = "mine"
    row["reviewers"] = {
        _login(r.get("author")): r["state"] for r in _nodes(node, "latestReviews")
        if _login(r.get("author")) not in (None, viewer) and r.get("submittedAt")
    }
    row["review_times"] = {
        _login(r.get("author")): r["submittedAt"] for r in _nodes(node, "latestReviews")
        if _login(r.get("author")) not in (None, viewer) and r.get("submittedAt")
    }
    row["requested"] = [
        _login(r.get("requestedReviewer")) or (r.get("requestedReviewer") or {}).get("slug")
        for r in _nodes(node, "reviewRequests") if r.get("requestedReviewer")
    ]
    row["unresolved"] = sum(1 for t in _nodes(node, "reviewThreads") if not t.get("isResolved"))
    row["mine_status"] = _mine_status(row)
    return row


def build_mine_rows(nodes: List[dict], viewer: str, now: datetime) -> List[dict]:
    rows = [build_mine_row(n, viewer, now) for n in nodes]
    rows.sort(key=lambda r: (MINE_ORDER.index(r["mine_status"]), r["created_at"]))
    for index, row in enumerate(rows, 1):
        row["index"] = index
    return rows
