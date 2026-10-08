"""Find the Claude Code session where the user built a PR's feature, so its review can be addressed there.

Claude Code stores each session as ~/.claude/projects/<dir>/<session-id>.jsonl, and every line records
`gitBranch` and `cwd`. An index (`sessions.json` in chip's cache) keeps, per session file, how many lines
were on each branch, the cwd used on it, the first prompt and the file's mtime; only new or changed files
are read again, within a time budget per refresh. A PR's feature session is the one that opened it (Claude
Code writes a `pr-link` line when a session creates a PR), else the one with the most activity on the PR's
head branch in that repo. A session the user links by hand (`links.json`) always wins.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Dict, List, Optional

from chip import files

BRANCH_RE = re.compile(r'"gitBranch":"([^"]*)"')
CWD_RE = re.compile(r'"cwd":"([^"]*)"')
PR_LINK_RE = re.compile(r'"type":\s*"pr-link"')
TRUNKS = {"", "HEAD", "main", "master", "dev", "develop", "staging", "build-staging"}
SKIP_DIRS = ("-cache-chip-worktrees-",)  # chip's own review sessions


def projects_dir() -> Path:
    return Path(os.environ.get("CHIP_CLAUDE_PROJECTS") or Path.home() / ".claude" / "projects")


def _load(path) -> dict:
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _save(path, data: dict) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    files.write_atomic(Path(path), json.dumps(data))


def _first_prompt(line: str) -> str:
    try:
        content = json.loads(line).get("message", {}).get("content")
    except ValueError:
        return ""
    if isinstance(content, list):
        content = " ".join(part.get("text", "") for part in content if isinstance(part, dict))
    text = " ".join(str(content or "").split())
    return text if not text.startswith("<") else ""  # skip command/meta wrappers


def _pr_link(line: str) -> str:
    """`owner/repo#number` of a `pr-link` line (lowercased), or ""."""
    try:
        entry = json.loads(line)
    except ValueError:
        return ""
    repo, number = entry.get("prRepository"), entry.get("prNumber")
    return f"{repo.lower()}#{number}" if isinstance(repo, str) and isinstance(number, int) else ""


def scan(file: Path) -> dict:
    """Branch activity, cwd per branch, PRs it opened, first prompt and last time of one session file."""
    branches: Dict[str, int] = {}
    cwds: Dict[str, str] = {}
    prs: List[str] = []
    prompt, last, start = "", "", ""
    with open(file, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            branch = BRANCH_RE.search(line)
            if branch:
                name = branch.group(1)
                branches[name] = branches.get(name, 0) + 1
                cwd = CWD_RE.search(line)
                if cwd:
                    cwds[name] = cwd.group(1)
            if not start:
                cwd = CWD_RE.search(line)
                start = cwd.group(1) if cwd else ""
            if PR_LINK_RE.search(line):
                pr = _pr_link(line)
                if pr and pr not in prs:
                    prs.append(pr)
            if not prompt and '"type":"user"' in line:
                prompt = _first_prompt(line)
            stamp = re.search(r'"timestamp":"([^"]+)"', line)
            if stamp:
                last = stamp.group(1)
    return {"branches": branches, "cwds": cwds, "prs": prs, "prompt": prompt[:80], "last": last, "start": start}


def update_index(path, budget: float = 1.5, root: Optional[Path] = None) -> dict:
    """Read new or changed session files into the index, for at most `budget` seconds."""
    root = root or projects_dir()
    index = _load(path)
    files = index.setdefault("files", {})
    deadline = time.monotonic() + budget
    changed = False
    seen = set()
    for file in sorted(root.glob("*/*.jsonl"), key=lambda f: -f.stat().st_mtime):
        if any(skip in file.parent.name for skip in SKIP_DIRS):
            continue
        key = str(file)
        seen.add(key)
        mtime = file.stat().st_mtime
        known = files.get(key, {})
        if known.get("mtime") == mtime and "prs" in known:  # an entry without "prs" predates PR links
            continue
        if time.monotonic() > deadline:
            break  # the rest on the next refresh
        files[key] = dict(scan(file), mtime=mtime)
        changed = True
    for key in [k for k in files if k not in seen and not Path(k).exists()]:
        del files[key]
        changed = True
    if changed:
        _save(path, index)
    return index


def _session(key: str, info: dict, branch: str) -> dict:
    """`cwd` is where the session started: `claude --resume <id>` only finds it from there."""
    return {"id": Path(key).stem, "cwd": info.get("start") or info["cwds"].get(branch, ""),
            "branch": branch, "prompt": info.get("prompt", ""), "last": info.get("last", ""), "file": key}


def find(index: dict, branch: str, clone: Optional[str] = None) -> Optional[dict]:
    """The session with the most activity on `branch` (in this repo when its clone path is known)."""
    if branch in TRUNKS:
        return None
    best = None
    for key, info in index.get("files", {}).items():
        count = info.get("branches", {}).get(branch, 0)
        if not count:
            continue
        cwds = [info.get("cwds", {}).get(branch, ""), info.get("start", "")]
        if clone and not any(c.startswith(clone.rstrip("/")) for c in cwds):
            continue
        rank = (count, info.get("last", ""))
        if best is None or rank > best[0]:
            best = (rank, key, info)
    return _session(best[1], best[2], branch) if best else None


def find_by_pr(index: dict, repo: str, number: int) -> Optional[dict]:
    """The session that opened `repo#number` (the latest, should several have), or None."""
    pr = f"{repo.lower()}#{number}"
    best = None
    for key, info in index.get("files", {}).items():
        if pr in info.get("prs", []) and (best is None or info.get("last", "") > best[1].get("last", "")):
            best = (key, info)
    if best is None:
        return None
    branches = best[1].get("branches") or {"": 1}
    return _session(best[0], best[1], max(branches, key=branches.get))


def by_id(index: dict, session_id: str, root: Optional[Path] = None) -> Optional[dict]:
    """A session by id, from the index or the projects folder."""
    for key, info in index.get("files", {}).items():
        if Path(key).stem == session_id:
            branch = max(info.get("branches", {"": 1}), key=info.get("branches", {"": 1}).get)
            return _session(key, info, branch)
    for file in (root or projects_dir()).glob(f"*/{session_id}.jsonl"):
        info = scan(file)
        branch = max(info["branches"] or {"": 1}, key=(info["branches"] or {"": 1}).get)
        return _session(str(file), info, branch)
    return None


def load_links(path) -> Dict[str, dict]:
    return _load(path)


def link(path, label: str, session: dict) -> None:
    links = _load(path)
    links[label] = session
    _save(path, links)


def unlink(path, label: str) -> None:
    links = _load(path)
    links.pop(label, None)
    _save(path, links)


def for_rows(rows: List[dict], index: dict, links: Dict[str, dict], clones: Dict[str, str]) -> Dict[str, dict]:
    """label → feature session (linked by hand, else the one that opened the PR, else found by branch)."""
    found = {}
    for row in rows:
        session = links.get(row["label"])
        if session:
            found[row["label"]] = dict(session, linked=True)
            continue
        session = (find_by_pr(index, row["repo"], row["number"]) if row.get("number") else None) \
            or find(index, row.get("head", ""), clones.get(row["repo"].lower()))
        if session:
            found[row["label"]] = dict(session, linked=False)
    return found
