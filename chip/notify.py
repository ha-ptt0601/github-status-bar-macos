"""Diff menu state between refreshes and raise macOS notifications (English)."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

from chip import model

LIMIT = 3


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
        "mine": {r["label"]: {"status": r["mine_status"], "title": r["title"],
                              "reviews": {login: [state, r.get("review_times", {}).get(login)]
                                          for login, state in r["reviewers"].items()}}
                 for r in mine or []},
    }


def _mine_messages(prev: Optional[dict], cur: dict) -> List[str]:
    """Reviews on the user's own PRs, CI failures and conflicts; silent for PRs not seen before."""
    if prev is None:
        return []
    messages = []
    for label, now in cur.items():
        before = prev.get(label)
        if before is None:
            continue
        what = f"{label} — {_short(now['title'])}"
        for login, (state, at) in now["reviews"].items():
            if before["reviews"].get(login) != [state, at] and state in REVIEW_VERB:
                messages.append(f"{login} {REVIEW_VERB[state]} {what}")
        if now["status"] in MINE_ALERTS and before["status"] != now["status"]:
            messages.append(f"{MINE_ALERTS[now['status']]} {what}")
    return messages


def diff(prev: Optional[dict], cur: dict, rows: List[dict], records: Dict[str, dict]) -> List[str]:
    if prev is None:
        return []
    by_label = {r["label"]: r for r in rows}
    messages = []
    for label, status in cur["prs"].items():
        before = prev.get("prs", {}).get(label)
        row = by_label[label]
        if status == model.NEW and before is None:
            messages.append(f"New review request: {label} — {_short(row['title'])} by {row['author']}")
        elif status == model.REREVIEW and before != model.REREVIEW:
            messages.append(f"Needs re-review: {label} — {_short(row['title'])}")
    for key, kind in cur["runs"].items():
        if kind == prev.get("runs", {}).get(key) or key not in records:
            continue
        record = records[key]
        if kind == "done":
            messages.append(f"Review finished: {record['label']} ({record['skill']})")
        elif kind == "needs_you":
            messages.append(f"Review needs you: {record['label']} ({record['skill']})")
    messages += _mine_messages(prev.get("mine"), cur.get("mine", {}))
    if cur["update"] and cur["update"] != prev.get("update"):
        messages.append(f"chip v{cur['update']} is available")
    return messages


def cap(messages: List[str], limit: int = LIMIT) -> List[str]:
    if len(messages) <= limit:
        return messages
    return messages[:limit] + [f"+{len(messages) - limit} more"]


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
