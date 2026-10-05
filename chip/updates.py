"""Release check against the GitHub repo, and self-update: a clone pulls (fast-forward) and rebuilds; the
app from the .dmg downloads the release's GitHubBar.dmg and swaps itself."""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from chip import files

REPO = os.environ.get("CHIP_UPDATE_REPO", "ha-ptt0601/github-status-bar-macos")
CHECK_EVERY_SECONDS = 6 * 3600
VERSION_RE = re.compile(r'^__version__ = "([^"]+)"', re.M)
DMG = "GitHubBar.dmg"
# Run detached once chip has unpacked the new app: quit GitHubBar, swap the bundles (putting the old one
# back if the move fails) and open the new one. $1 is the installed app, $2 the new one.
SWAP = """
osascript -e 'quit app id "com.ha-ptt0601.githubbar"' >/dev/null 2>&1
for _ in $(seq 40); do pgrep -f "$1/Contents/MacOS/" >/dev/null || break; sleep 0.25; done
rm -rf "$1.old"
if mv "$1" "$1.old" && mv "$2" "$1"; then rm -rf "$1.old"; else mv "$1.old" "$1"; fi
xattr -dr com.apple.quarantine "$1" 2>/dev/null
open "$1"
"""


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
    files.write_atomic(cache_path, json.dumps({"checked_at": now, "latest": latest}))
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


def _detached(cmd: List[str]) -> None:
    subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)


def update_app(app: Path, version: str, runner=None, spawn: Callable[[List[str]], None] = _detached,
               work: Optional[Path] = None) -> Tuple[bool, str]:
    """Download release `version`'s GitHubBar.dmg, copy the app out of it, then swap it in (detached, since
    GitHubBar quits on the way)."""
    runner = runner or subprocess.run
    work = Path(work or tempfile.mkdtemp(prefix="githubbar-update-"))
    got = runner(["gh", "release", "download", f"v{version}", "--repo", REPO, "--pattern", DMG,
                  "--dir", str(work), "--clobber"], capture_output=True, text=True)
    if got.returncode != 0:
        return False, (got.stderr or got.stdout).strip() or f"could not download {DMG}"
    mount = work / "mnt"
    attach = runner(["hdiutil", "attach", "-nobrowse", "-readonly", "-mountpoint", str(mount), str(work / DMG)],
                    capture_output=True, text=True)
    if attach.returncode != 0:
        return False, (attach.stderr or attach.stdout).strip() or f"could not open {DMG}"
    new = work / Path(app).name
    try:
        copy = runner(["ditto", str(mount / "GitHubBar.app"), str(new)], capture_output=True, text=True)
    finally:
        runner(["hdiutil", "detach", str(mount)], capture_output=True, text=True)
    if copy.returncode != 0:
        return False, (copy.stderr or copy.stdout).strip() or "could not copy the new app"
    spawn(["/bin/sh", "-c", SWAP, "swap", str(app), str(new)])
    return True, f"Updating GitHubBar to v{version}…"
