"""Inbox cache shared by every command: fetch once, keep ALL rows, hand out filtered views."""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

from chip import fetch, menu, model

CACHE_TTL_SECONDS = 180


def cache_dir() -> Path:
    return Path(os.environ.get("CHIP_CACHE_DIR") or Path.home() / ".cache" / "chip")


def work_root() -> Path:
    if os.environ.get("CHIP_WORK_ROOT"):
        return Path(os.environ["CHIP_WORK_ROOT"])
    from chip import config  # imported lazily: config imports nothing from store, but keep store light
    return Path(config.load()["work_root"])


def _last() -> Path:
    return cache_dir() / "last.json"


def cached_all() -> Optional[dict]:
    try:
        return json.loads(_last().read_text())
    except (OSError, ValueError):
        return None


def load_all(runner, force: bool = False) -> Tuple[Optional[dict], Optional[str]]:
    """All rows, approved and drafts included. Reuses a fetch younger than CACHE_TTL_SECONDS
    unless `force`. On a fetch error, returns the stale cache (or None) and the error text."""
    cached = cached_all()
    fresh = (cached and cached.get("all_rows") and "mine" in cached
             and time.time() - cached.get("fetched_at", 0) < CACHE_TTL_SECONDS)
    if not force and fresh:
        return cached, None
    try:
        viewer, nodes, mine_nodes = fetch.fetch_all(runner)
    except fetch.FetchError as exc:
        return (cached if cached and cached.get("all_rows") else None), str(exc)
    now = datetime.now(timezone.utc)
    inbox = model.build_inbox(nodes, viewer, now, show_all=True)
    menu.assign_labels(inbox["rows"])
    inbox["mine"] = menu.assign_labels(model.build_mine_rows(mine_nodes, viewer, now))
    inbox["fetched_at"] = time.time()
    inbox["all_rows"] = True
    cache_dir().mkdir(parents=True, exist_ok=True)
    _last().write_text(json.dumps(inbox, ensure_ascii=False, indent=1))
    return inbox, None


def load_query() -> str:
    """The menu's current search text ("" when none)."""
    try:
        return json.loads((cache_dir() / "filter.json").read_text()).get("q", "")
    except (OSError, ValueError):
        return ""


def save_query(query: str) -> None:
    cache_dir().mkdir(parents=True, exist_ok=True)
    (cache_dir() / "filter.json").write_text(json.dumps({"q": query.strip()}, ensure_ascii=False))


VIEWS = ("review", "mine")


def load_view() -> str:
    """The menu tab to show: `review` (default) or `mine`."""
    try:
        view = json.loads((cache_dir() / "view.json").read_text()).get("view")
    except (OSError, ValueError):
        view = None
    return view if view in VIEWS else "review"


def save_view(view: str) -> None:
    cache_dir().mkdir(parents=True, exist_ok=True)
    (cache_dir() / "view.json").write_text(json.dumps({"view": view}))
