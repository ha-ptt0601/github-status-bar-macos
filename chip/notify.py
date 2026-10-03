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


def snapshot(rows: List[dict], run_views: Dict[str, dict], newer: Optional[str]) -> dict:
    return {
        "prs": {r["label"]: r["status"] for r in rows},
        "runs": {key: view["kind"] for key, view in run_views.items()},
        "update": newer or "",
    }


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
