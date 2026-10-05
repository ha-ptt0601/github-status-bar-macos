"""Fetch open PRs waiting on the viewer through `gh api graphql`."""
from __future__ import annotations

import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Dict, List, Optional, Tuple

# reviewed-by is needed: submitting a review removes you from review-requested.
SEARCHES = (
    "is:pr is:open review-requested:@me -author:@me",
    "is:pr is:open reviewed-by:@me -author:@me",
)

MINE_SEARCH = "is:pr is:open author:@me"

QUERY = """
query($q: String!, $after: String) {
  viewer { login }
  search(query: $q, type: ISSUE, first: 50, after: $after) {
    pageInfo { hasNextPage endCursor }
    nodes {
      ... on PullRequest {
        id number title url isDraft createdAt
        author { login }
        repository { nameWithOwner defaultBranchRef { name } primaryLanguage { name } }
        baseRefName headRefName
        additions deletions changedFiles mergeable reviewDecision
        commits(last: 1) { nodes { commit { committedDate statusCheckRollup { state } } } }
        latestReviews(first: 20) { nodes { author { login } state submittedAt } }
        reviewRequests(first: 20) { nodes { requestedReviewer { ... on User { login } ... on Team { slug } } } }
        reviewThreads(first: 100) { totalCount nodes { isResolved } }
      }
    }
  }
}
"""

Runner = Callable[[str, Optional[str]], dict]


class FetchError(RuntimeError):
    pass


TIMEOUT = 45


def run_gh_graphql(search: str, after: Optional[str]) -> dict:
    cmd = ["gh", "api", "graphql", "-f", f"query={QUERY}", "-f", f"q={search}"]
    if after:
        cmd += ["-f", f"after={after}"]
    for attempt in (1, 2):
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)
            break
        except FileNotFoundError:
            raise FetchError("gh command not found")
        except subprocess.TimeoutExpired:
            # Usually the Mac slept during the call (the timeout counts wall time) or the network is
            # still waking up: try once more before giving up.
            if attempt == 2:
                raise FetchError(f"GitHub did not answer within {TIMEOUT}s (offline, or the Mac just woke up)")
    if proc.returncode != 0:
        raise FetchError(proc.stderr.strip() or f"gh exited with code {proc.returncode}")
    data = json.loads(proc.stdout)
    if data.get("errors"):
        raise FetchError("; ".join(e.get("message", "") for e in data["errors"]))
    return data["data"]


def search_all(search: str, runner: Runner) -> Tuple[str, List[dict]]:
    nodes: List[dict] = []
    after = None
    while True:
        data = runner(search, after)
        page = data["search"]
        nodes.extend(n for n in page["nodes"] if n.get("id"))
        if not page["pageInfo"]["hasNextPage"]:
            return data["viewer"]["login"], nodes
        after = page["pageInfo"]["endCursor"]


def fetch_inbox_nodes(runner: Runner = run_gh_graphql) -> Tuple[str, List[dict]]:
    # Both searches run in parallel (~5s instead of ~8s); results merge in SEARCHES order.
    with ThreadPoolExecutor(max_workers=len(SEARCHES)) as pool:
        results = list(pool.map(lambda search: search_all(search, runner), SEARCHES))
    seen: Dict[str, dict] = {}
    for _, nodes in results:
        for node in nodes:
            seen.setdefault(node["id"], node)
    return results[-1][0], list(seen.values())


def fetch_all(runner: Runner = run_gh_graphql) -> Tuple[str, List[dict], List[dict]]:
    """Viewer, PRs waiting on the viewer's review (deduped), and the viewer's own open PRs — fetched in parallel."""
    searches = list(SEARCHES) + [MINE_SEARCH]
    with ThreadPoolExecutor(max_workers=len(searches)) as pool:
        results = list(pool.map(lambda search: search_all(search, runner), searches))
    seen: Dict[str, dict] = {}
    for _, nodes in results[:-1]:
        for node in nodes:
            seen.setdefault(node["id"], node)
    return results[0][0], list(seen.values()), results[-1][1]
