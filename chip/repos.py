"""Find (or clone) the local checkout of a GitHub repo."""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Dict, Optional

REMOTE_RE = re.compile(r"github\.com[:/]+([^/\s]+)/([^/\s]+?)(?:\.git)?/?$")
SKIP_DIRS = {"node_modules", "vendor"}
CLONE_DIR = ".chip-repos"


class CloneError(RuntimeError):
    pass


def normalize_remote(url: str) -> Optional[str]:
    match = REMOTE_RE.search(url.strip())
    return f"{match.group(1)}/{match.group(2)}".lower() if match else None


def origin_of(path) -> Optional[str]:
    proc = subprocess.run(
        ["git", "-C", str(path), "remote", "get-url", "origin"], capture_output=True, text=True
    )
    return normalize_remote(proc.stdout) if proc.returncode == 0 else None


def scan(root, max_depth: int = 3) -> Dict[str, str]:
    """Map owner/repo -> path for git repos up to max_depth below root (hidden dirs skipped)."""
    root = Path(root)
    found: Dict[str, str] = {}
    if not root.is_dir():
        return found
    base_depth = len(root.parts)
    for dirpath, dirnames, _ in os.walk(root):
        path = Path(dirpath)
        if path != root and (path / ".git").exists():
            slug = origin_of(path)
            if slug:
                found.setdefault(slug, str(path))
            dirnames[:] = []
        elif len(path.parts) - base_depth >= max_depth:
            dirnames[:] = []
        else:
            dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and d not in SKIP_DIRS)
    return found


def _load(cache) -> Dict[str, str]:
    try:
        return json.loads(Path(cache).read_text())
    except (OSError, ValueError):
        return {}


def _save(cache, data: Dict[str, str]) -> None:
    cache = Path(cache)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(data, indent=1, sort_keys=True))


def _clone_target(slug: str, work_root) -> Path:
    return Path(work_root) / CLONE_DIR / slug.split("/")[1]


def resolve(slug: str, work_root, cache) -> Optional[str]:
    slug = slug.lower()
    known = _load(cache)
    cached = known.get(slug)
    if cached and Path(cached).is_dir() and origin_of(cached) == slug:
        return cached
    found = scan(work_root)
    target = _clone_target(slug, work_root)
    if target.is_dir() and origin_of(target) == slug:
        found.setdefault(slug, str(target))
    known.pop(slug, None)
    known.update(found)
    _save(cache, known)
    return found.get(slug)


def clone(slug: str, work_root, cache, runner=subprocess.run) -> str:
    slug = slug.lower()
    target = _clone_target(slug, work_root)
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        proc = runner(["gh", "repo", "clone", slug, str(target)], capture_output=True, text=True)
        if proc.returncode != 0:
            raise CloneError(proc.stderr.strip() or f"gh repo clone {slug} failed")
    if origin_of(target) != slug:
        raise CloneError(f"{target} exists but is not {slug}")
    known = _load(cache)
    known[slug] = str(target)
    _save(cache, known)
    return str(target)
