"""Find (or clone) the local checkout of a GitHub repo."""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

from chip import files

REMOTE_RE = re.compile(r"github\.com[:/]+([^/\s]+)/([^/\s]+?)(?:\.git)?/?$")
SKIP_DIRS = {"node_modules", "vendor"}
CLONE_DIR = ".chip-repos"  # where chip cloned before v0.1.2 (<work_root>/.chip-repos); still recognised


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
    files.write_atomic(cache, json.dumps(data, indent=1, sort_keys=True))


def _roots(roots) -> List[Path]:
    return [Path(roots)] if isinstance(roots, (str, Path)) else [Path(r) for r in roots]


def resolve(slug: str, roots, cache, clone_root=None) -> Optional[str]:
    """The local clone of owner/repo: remembered in `cache`, else found under `roots` (a folder or a list)
    or in `clone_root` (chip's own clones; older versions used <root>/.chip-repos). Found clones are remembered."""
    slug = slug.lower()
    known = _load(cache)
    cached = known.get(slug)
    if cached and Path(cached).is_dir() and origin_of(cached) == slug:
        return cached
    found: Dict[str, str] = {}
    for root in _roots(roots):
        for name, path in scan(root).items():
            found.setdefault(name, path)
    name = slug.split("/")[1]
    targets = ([Path(clone_root) / name] if clone_root else []) + [r / CLONE_DIR / name for r in _roots(roots)]
    for target in targets:
        if slug not in found and target.is_dir() and origin_of(target) == slug:
            found[slug] = str(target)
    known.pop(slug, None)
    known.update(found)
    _save(cache, known)
    return found.get(slug)


def clone(slug: str, clone_root, cache, runner=subprocess.run) -> str:
    """Clone owner/repo into `clone_root`/<repo> (with the user's gh credentials) and remember it."""
    slug = slug.lower()
    target = Path(clone_root) / slug.split("/")[1]
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        # Partial clone: history without file contents, which git fetches on demand. Much faster for big repos.
        proc = runner(["gh", "repo", "clone", slug, str(target), "--", "--filter=blob:none"],
                      capture_output=True, text=True)
        if proc.returncode != 0:
            raise CloneError(proc.stderr.strip() or f"gh repo clone {slug} failed")
    if origin_of(target) != slug:
        raise CloneError(f"{target} exists but is not {slug}")
    known = _load(cache)
    known[slug] = str(target)
    _save(cache, known)
    return str(target)
