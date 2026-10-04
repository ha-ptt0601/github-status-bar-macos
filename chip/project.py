"""A repository's own review skill, and the per-PR git worktree every chip run happens in.

Every run (configured skill, the repo's own skill, or the built-in review) gets the PR checked out in its own
worktree under ~/.cache/chip/worktrees/, so Claude reads the PR's code without touching the user's clone.
Repo skills such as `.claude/skills/review` review the checked-out branch, which this makes the PR.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Dict, Iterable, Optional

from chip import repos

# Appended to every run's prompt template ({number} and {base} are filled per PR).
NOTE = (
    "\n\nThis directory is a git worktree with pull request #{number} checked out at HEAD. Its base branch is "
    "origin/{base}: compare against it (git diff origin/{base}...HEAD), not against main."
)


class WorktreeError(Exception):
    pass


def find_review_skill(repo_path) -> Optional[str]:
    """Name of the repo's review skill or command (`.claude/skills/*review*/SKILL.md`,
    `.claude/commands/*review*.md`); one named exactly "review" wins."""
    root = Path(repo_path) / ".claude"
    names = [p.parent.name for p in sorted(root.glob("skills/*/SKILL.md")) if "review" in p.parent.name.lower()]
    names += [p.stem for p in sorted(root.glob("commands/*.md")) if "review" in p.stem.lower()]
    if not names:
        return None
    return "review" if "review" in names else names[0]


def known_skills(slugs: Iterable[str], cache) -> Dict[str, str]:
    """Review skills of repos already cloned (from the clone cache; never scans or clones)."""
    known = repos._load(cache)
    found = {}
    for slug in set(slugs):
        path = known.get(slug.lower())
        name = find_review_skill(path) if path and Path(path).is_dir() else None
        if name:
            found[slug] = name
    return found


def skill_label(skill: str) -> str:
    """How a project skill is named on buttons and in "Reviews by GitHubBar"."""
    return f"/{skill} (project)"


def prompt_template(skill: str) -> str:
    """The run prompt for a project skill; `{url}`, `{number}` and `{base}` are filled per PR."""
    return f"/{skill} {{url}}"


def in_worktree(skill: dict) -> dict:
    """The skill with the worktree note added to its prompt."""
    return dict(skill, prompt=skill["prompt"] + NOTE)


def worktree_path(row: dict, root) -> Path:
    return Path(root) / f"{row['repo'].split('/')[-1]}-{row['number']}"


def _git(args, runner, cwd=None) -> subprocess.CompletedProcess:
    proc = runner(["git", *args], cwd=cwd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise WorktreeError((proc.stderr or proc.stdout or f"git {' '.join(args)} failed").strip())
    return proc


# Copied (not linked) from the clone: it enables the repo's MCP servers and holds the user's permissions.
LOCAL_SETTINGS = ".claude/settings.local.json"


def prepare(clone, worktree, links=()) -> None:
    """Give the worktree what git does not: the clone's local Claude settings (copied) and `links`
    (e.g. .env, vendor, node_modules) as symlinks to the clone. Missing sources and paths the
    worktree already has are skipped."""
    clone, worktree = Path(clone), Path(worktree)
    settings = clone / LOCAL_SETTINGS
    if settings.is_file():
        (worktree / LOCAL_SETTINGS).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(settings, worktree / LOCAL_SETTINGS)
    for name in links:
        source, target = clone / name, worktree / name
        if source.exists() and not (target.exists() or target.is_symlink()):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.symlink_to(source)


def checkout(clone, row: dict, root, runner=None, links=()) -> str:
    """Fetch the PR head and its base, (re)check the PR out, detached, in its own worktree, and prepare it."""
    runner = runner or subprocess.run
    ref = f"refs/chip/pr-{row['number']}"
    _git(["-C", str(clone), "fetch", "--quiet", "origin", f"+refs/pull/{row['number']}/head:{ref}",
          f"+refs/heads/{row['base']}:refs/remotes/origin/{row['base']}"], runner)
    target = worktree_path(row, root)
    if (target / ".git").exists():
        _git(["-C", str(target), "checkout", "--quiet", "--detach", "--force", ref], runner)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        _git(["-C", str(clone), "worktree", "add", "--quiet", "--detach", str(target), ref], runner)
    prepare(clone, target, links)
    return str(target)


def remove(clone, path, number=None, runner=None) -> None:
    """Remove a PR worktree and the ref chip fetched for it."""
    runner = runner or subprocess.run
    runner(["git", "-C", str(clone), "worktree", "remove", "--force", str(path)], capture_output=True, text=True)
    if number is not None:
        runner(["git", "-C", str(clone), "update-ref", "-d", f"refs/chip/pr-{number}"], capture_output=True, text=True)
