"""Near-real-time updates from GitHub Notifications.

Every refresh asks `GET /notifications` with `If-Modified-Since`. Nothing new answers `304 Not Modified`,
which does not count against the rate limit. A new or updated pull-request notification (review request,
review or comment on the user's PR, mention, merge, CI) makes the caller fetch everything at once instead
of waiting for the inbox cache to expire. GitHub's `X-Poll-Interval` (usually 60 s) is respected.
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Optional, Tuple

# Notification reasons that can change what the menu shows.
REASONS = {"review_requested", "author", "comment", "mention", "team_mention", "state_change", "ci_activity",
           "assign", "manual", "subscribed"}
FALLBACK_POLL = 60
RETRY_AFTER_ERROR = 300


def _load(path) -> dict:
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _save(path, state: dict) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(state))


def parse_response(text: str) -> Tuple[int, dict, str]:
    """`gh api -i` output → (HTTP status, lower-case headers, body)."""
    head, _, body = text.replace("\r\n", "\n").partition("\n\n")
    lines = head.split("\n")
    try:
        status = int(lines[0].split()[1])
    except (IndexError, ValueError):
        return 0, {}, text
    headers = {}
    for line in lines[1:]:
        key, sep, value = line.partition(":")
        if sep:
            headers[key.strip().lower()] = value.strip()
    return status, headers, body


def check(path, runner=None, now: Optional[float] = None) -> Optional[bool]:
    """True: a relevant PR notification is new since the last check (fetch now). False: nothing new, or
    it is too early to ask again. None: notifications are not available (the caller keeps its usual pace)."""
    runner = runner or subprocess.run
    now = time.time() if now is None else now
    state = _load(path)
    if now < state.get("next_at", 0):
        return False if state.get("ok", True) else None
    cmd = ["gh", "api", "-i", "notifications"]
    if state.get("last_modified"):
        cmd += ["-H", f"If-Modified-Since: {state['last_modified']}"]
    try:
        proc = runner(cmd, capture_output=True, text=True, timeout=20)
        output = proc.stdout or ""
    except (OSError, subprocess.TimeoutExpired):
        output = ""
    status, headers, body = parse_response(output)  # gh exits 1 on 304, so read the status line instead
    try:
        poll = int(headers.get("x-poll-interval", FALLBACK_POLL))
    except ValueError:
        poll = FALLBACK_POLL
    if status == 304:
        _save(path, dict(state, ok=True, next_at=now + poll))
        return False
    if status != 200:
        _save(path, dict(state, ok=False, next_at=now + RETRY_AFTER_ERROR))
        return None
    try:
        items = json.loads(body or "[]")
    except ValueError:
        items = []
    seen = state.get("last_seen", "")
    fresh = [n for n in items if isinstance(n, dict) and n.get("updated_at", "") > seen
             and (n.get("subject") or {}).get("type") == "PullRequest" and n.get("reason") in REASONS]
    newest = max([seen] + [n.get("updated_at", "") for n in items if isinstance(n, dict)])
    first = "last_modified" not in state
    _save(path, {"ok": True, "next_at": now + poll, "last_modified": headers.get("last-modified", ""),
                 "last_seen": newest})
    return bool(fresh) and not first
