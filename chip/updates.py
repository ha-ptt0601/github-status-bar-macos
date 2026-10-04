"""Release check against the private GitHub repo and fast-forward self-update."""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Optional, Tuple

REPO = os.environ.get("CHIP_UPDATE_REPO", "ha-ptt0601/github-status-bar-macos")
CHECK_EVERY_SECONDS = 6 * 3600
VERSION_RE = re.compile(r'^__version__ = "([^"]+)"', re.M)


def parse_version(value: str) -> Tuple[int, ...]:
    try:
        return tuple(int(part) for part in value.strip().lstrip("v").split("."))
    except ValueError:
        return (0,)


def is_newer(latest: str, current: str) -> bool:
    return parse_version(latest) > parse_version(current)


def read_version(repo_dir: Path) -> str:
    match = VERSION_RE.search((Path(repo_dir) / "chip" / "__init__.py").read_text())
    return match.group(1) if match else "0"


def latest_release(cache_path, runner=None, now: float = 0.0, force: bool = False) -> Optional[str]:
    """Latest release tag without the `v` (None if none), checked at most every 6 hours."""
    runner = runner or subprocess.run
    cache_path = Path(cache_path)
    try:
        cached = json.loads(cache_path.read_text())
    except (OSError, ValueError):
        cached = None
    if not force and cached and now - cached.get("checked_at", 0) < CHECK_EVERY_SECONDS:
        return cached.get("latest")
    try:
        proc = runner(["gh", "api", f"repos/{REPO}/releases/latest", "--jq", ".tag_name"],
                      capture_output=True, text=True, timeout=20)
        tag = proc.stdout.strip() if proc.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        tag = ""
    latest = tag.lstrip("v") or None
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps({"checked_at": now, "latest": latest}))
    return latest


def update_repo(repo_dir: str, runner=None) -> Tuple[bool, str]:
    runner = runner or subprocess.run
    status = runner(["git", "-C", str(repo_dir), "status", "--porcelain"], capture_output=True, text=True)
    if status.stdout.strip():
        return False, "local changes in the chip repo; commit or stash them first"
    pull = runner(["git", "-C", str(repo_dir), "pull", "--ff-only"], capture_output=True, text=True)
    if pull.returncode != 0:
        return False, (pull.stderr or pull.stdout).strip() or "git pull failed"
    return True, pull.stdout.strip()
