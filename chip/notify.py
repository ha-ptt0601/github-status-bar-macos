"""Diff menu state between refreshes and raise macOS notifications (English).

An event is {"text", "href"} (open the PR) or {"text", "run"} (open the review session).
Events are remembered for the "Recent notifications" menu. Under GitHubBar (GITHUBBAR_NOTIFY=1)
they go to an outbox that the app drains and posts natively, so clicking one opens its link.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

from chip import model

LIMIT = 3
HISTORY = 10
RELEASES_URL = "https://github.com/ha-ptt0601/github-status-bar-macos/releases/latest"


def _short(text: str, width: int = 60) -> str:
    return text if len(text) <= width else text[: width - 1] + "…"


REVIEW_VERB = {"APPROVED": "approved", "CHANGES_REQUESTED": "requested changes on", "COMMENTED": "commented on"}
MINE_ALERTS = {model.CI_FAILED: "CI failed on", model.CONFLICT: "Conflict on"}


def snapshot(rows: List[dict], run_views: Dict[str, dict], newer: Optional[str],
             mine: Optional[List[dict]] = None) -> dict:
    return {
        "prs": {r["label"]: r["status"] for r in rows},
        "runs": {key: view["kind"] for key, view in run_views.items()},
        "update": newer or "",
        "mine": {r["label"]: {"status": r["mine_status"], "title": r["title"], "url": r.get("url", ""),
                              "reviews": {login: [state, r.get("review_times", {}).get(login)]
                                          for login, state in r["reviewers"].items()}}
                 for r in mine or []},
    }


def _event(text: str, href: str = "", run: str = "") -> dict:
    event = {"text": text}
    if run:
        event["run"] = run
    elif href:
        event["href"] = href
    return event


def _mine_events(prev: Optional[dict], cur: dict) -> List[dict]:
    """Reviews on the user's own PRs, CI failures and conflicts; silent for PRs not seen before."""
    if prev is None:
        return []
    events = []
    for label, now in cur.items():
        before = prev.get(label)
        if before is None:
            continue
        what = f"{label} — {_short(now['title'])}"
        for login, (state, at) in now["reviews"].items():
            if before["reviews"].get(login) != [state, at] and state in REVIEW_VERB:
                events.append(_event(f"{login} {REVIEW_VERB[state]} {what}", now.get("url", "")))
        if now["status"] in MINE_ALERTS and before["status"] != now["status"]:
            events.append(_event(f"{MINE_ALERTS[now['status']]} {what}", now.get("url", "")))
    return events


def events(prev: Optional[dict], cur: dict, rows: List[dict], records: Dict[str, dict]) -> List[dict]:
    if prev is None:
        return []
    by_label = {r["label"]: r for r in rows}
    found = []
    for label, status in cur["prs"].items():
        before = prev.get("prs", {}).get(label)
        row = by_label[label]
        if status == model.NEW and before is None:
            found.append(_event(f"New review request: {label} — {_short(row['title'])} by {row['author']}",
                                row.get("url", "")))
        elif status == model.REREVIEW and before != model.REREVIEW:
            found.append(_event(f"Needs re-review: {label} — {_short(row['title'])}", row.get("url", "")))
    for key, kind in cur["runs"].items():
        if kind == prev.get("runs", {}).get(key) or key not in records:
            continue
        record = records[key]
        if kind == "done":
            found.append(_event(f"Review finished: {record['label']} ({record['skill']})", run=record.get("id", "")))
        elif kind == "needs_you":
            found.append(_event(f"Review needs you: {record['label']} ({record['skill']})", run=record.get("id", "")))
    found += _mine_events(prev.get("mine"), cur.get("mine", {}))
    if cur["update"] and cur["update"] != prev.get("update"):
        found.append(_event(f"GitHubBar v{cur['update']} is available", RELEASES_URL))
    return found


def diff(prev: Optional[dict], cur: dict, rows: List[dict], records: Dict[str, dict]) -> List[str]:
    return [event["text"] for event in events(prev, cur, rows, records)]


def cap(items: list, limit: int = LIMIT) -> list:
    """At most `limit` items plus a "+N more" one (a string or an event, like the items)."""
    if len(items) <= limit:
        return items
    more = f"+{len(items) - limit} more"
    return items[:limit] + [{"text": more} if isinstance(items[0], dict) else more]


def remember(path, new: List[dict], now: float, limit: int = HISTORY) -> None:
    """Prepend events (stamped with `at`) to the recent-notifications history."""
    history = load_list(path)
    _write(path, ([dict(event, at=now) for event in new] + history)[:limit])


def queue(path, new: List[dict]) -> None:
    """Add events to GitHubBar's outbox."""
    _write(path, load_list(path) + new)


def drain(path) -> List[dict]:
    """Take every event out of the outbox (GitHubBar posts them)."""
    pending = load_list(path)
    if pending:
        Path(path).unlink()
    return pending


def load_list(path) -> List[dict]:
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return []
    return data if isinstance(data, list) else []


def _write(path, data) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, ensure_ascii=False))


def send(messages: List[str], runner=None) -> None:
    runner = runner or subprocess.run
    for message in cap(messages):
        text = message.replace("\\", "\\\\").replace('"', '\\"')
        runner(["osascript", "-e", f'display notification "{text}" with title "chip"'],
               capture_output=True, text=True)


def load(path) -> Optional[dict]:
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None


def save(path, state: dict) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(state, ensure_ascii=False))
