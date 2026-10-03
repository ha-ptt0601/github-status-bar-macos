"""`chip` with no subcommand: pick a project, tick its PRs in fzf, then open claude per PR in its repo."""
from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Callable, List, Optional, Set

from chip import config, model
from chip.render import STATUS_LABEL

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
STATUS_COLOR = {
    model.REREVIEW: "33",   # yellow
    model.NEW: "32",        # green
    model.WAITING: "90",    # grey
    model.COMMENTED: "90",
    model.APPROVED: "36",   # cyan
}
ALL = "*"
NAME_WIDTH = 28
BIN = Path(__file__).resolve().parents[1] / "bin" / "chip"
CMD = f"{shlex.quote(sys.executable)} {shlex.quote(str(BIN))}"
# Preview on the right, or below when the window is narrower than 110 columns.
PREVIEW_WINDOW = "right,45%,wrap,border-rounded,<110(down,45%,wrap,border-rounded)"


def _c(code: str, text: str) -> str:
    return f"\x1b[{code}m{text}\x1b[0m"


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def load_picked(path) -> Set[int]:
    try:
        return set(json.loads(Path(path).read_text()))
    except (OSError, ValueError):
        return set()


def save_picked(path, picked: Set[int]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(sorted(picked)))


def toggle_picked(path, index: int) -> None:
    picked = load_picked(path)
    picked ^= {index}
    save_picked(path, picked)


def _short(full: str) -> str:
    return full.split("/")[-1]


def repo_lines(inbox: dict, picked: Set[int]) -> List[str]:
    """`repo<TAB>text` per repo (busiest first), after an `*` line for all repos."""
    rows = inbox["rows"]
    counts = Counter(r["repo"] for r in rows)

    def ticks(rs) -> str:
        n = sum(1 for r in rs if r["index"] in picked)
        return f"  {_c('32', f'☑ {n}')}" if n else ""

    lines = [f"{ALL}\t{'All'.ljust(NAME_WIDTH)} {len(rows)} PR{ticks(rows)}"]
    for full in sorted(counts, key=lambda f: (-counts[f], _short(f))):
        rs = [r for r in rows if r["repo"] == full]
        parts = [f"{counts[full]} PR"]
        rereview = sum(1 for r in rs if r["status"] == model.REREVIEW)
        if rereview:
            parts.append(_c(STATUS_COLOR[model.REREVIEW], f"{rereview} {STATUS_LABEL[model.REREVIEW]}"))
        newest = max(rs, key=lambda r: r.get("created_at", ""))
        parts.append(_c("90", f"newest {newest['wait']}"))
        lines.append(f"{full}\t{_short(full).ljust(NAME_WIDTH)} {' · '.join(parts)}{ticks(rs)}")
    return lines


def repo_preview(inbox: dict, repo: str) -> str:
    rows = [r for r in inbox["rows"] if repo == ALL or r["repo"] == repo]
    lines = []
    for r in rows:
        name = r["label"] if repo == ALL else f"#{r['number']}"
        lines.append(f"{name}  {_c(STATUS_COLOR[r['status']], STATUS_LABEL[r['status']])}  {_c('90', r['wait'])}")
        lines.append(f"  {r['title']}")
    return "\n".join(lines)


def pr_lines(inbox: dict, repo: str, picked: Set[int]) -> List[str]:
    """`index<TAB>☐/☑ #N  title  · author · wait · status …` for one repo (or all)."""
    lines = []
    for r in inbox["rows"]:
        if repo != ALL and r["repo"] != repo:
            continue
        box = _c("32", "☑") if r["index"] in picked else "☐"
        name = r["label"] if repo == ALL else f"#{r['number']}"
        meta = [r["author"], r["wait"], _c(STATUS_COLOR[r["status"]], STATUS_LABEL[r["status"]])]
        if r["jira"]:
            meta.append(_c("35", r["jira"]))
        if r["conflict"]:
            meta.append(_c("31", "conflict"))
        lines.append(f"{r['index']}\t{box} {name}  {r['title']}  {_c('90', '·')} {' · '.join(meta)}")
    return lines


def preview_text(r: dict) -> str:
    base = r["base"] + (" (stacked)" if r["stacked"] else "")
    fields = [
        ("Status", STATUS_LABEL[r["status"]]),
        ("Author", r["author"]),
        ("Waiting", r["wait"]),
        ("Decision", r["decision"]),
        ("Size", r["size"]),
        ("CI", r["ci"]),
        ("Merge", "conflict" if r["conflict"] else "ok"),
        ("Base", base),
        ("Jira", r["jira"] or "-"),
    ]
    head = [r["label"], "", r["title"], r["url"], ""]
    return "\n".join(head + [f"{k:<11} {v}" for k, v in fields])


def selected_indexes(output: str) -> List[int]:
    return [int(line.split("\t", 1)[0]) for line in output.splitlines() if line.strip()]


def run_fzf(kind: str, lines: List[str], header: str, repo: Optional[str] = None) -> subprocess.CompletedProcess:
    cmd = [
        # --exact + --no-sort: substring search (space = AND) that keeps the inbox priority order
        "fzf", "--ansi", "--exact", "--no-sort", "--delimiter=\t", "--with-nth=2..",
        "--border=rounded", "--border-label-pos=3", "--prompt=⌕ ", "--pointer=❯", "--info=inline-right",
        f"--header={header}", "--header-first", f"--preview-window={PREVIEW_WINDOW}",
    ]
    if kind == "repos":
        cmd += ["--border-label= chip · choose a project ", f"--preview={CMD} _repo-preview {{1}}"]
    else:
        label = "all projects" if repo == ALL else _short(repo)
        cmd += [
            f"--border-label= chip · {label} ", f"--preview={CMD} preview {{1}}",
            # Tab ticks via our own state file, then reloads so the ☐/☑ in the line updates;
            # --track/--id-nth keep the cursor on the same PR across the reload.
            "--track", "--id-nth=1",
            f"--bind=tab:execute-silent({CMD} _toggle {{1}})+reload({CMD} _prs {shlex.quote(repo)})+down",
        ]
    return subprocess.run(cmd, input="\n".join(lines), stdout=subprocess.PIPE, text=True)


def run_claude(prompt: str, cwd: str) -> None:
    subprocess.run(["claude", prompt], cwd=cwd)


def run_ui(
    inbox: dict,
    state_path,
    fzf: Callable = run_fzf,
    claude: Callable[[str, str], None] = run_claude,
    resolve: Callable[[str], Optional[str]] = None,
    clone: Callable[[str], str] = None,
    ask: Callable[[str], str] = input,
    out: Callable[[str], None] = print,
) -> int:
    rows = inbox["rows"]
    if not rows:
        out("Inbox zero 🎉")
        return 0
    hidden = inbox["hidden"]
    save_picked(state_path, set())
    repos_header = (f"{len(rows)} PRs · hidden: {hidden['approved']} approved, {hidden['draft']} draft"
                    "   Enter opens a project · Esc quits")
    prs_header = "Tab ticks ☐/☑ · Enter reviews ticked PRs · Esc goes back to projects"
    while True:
        result = fzf("repos", repo_lines(inbox, load_picked(state_path)), repos_header)
        if result.returncode != 0:
            return 0
        repo = result.stdout.split("\t", 1)[0].strip()
        result = fzf("prs", pr_lines(inbox, repo, load_picked(state_path)), prs_header, repo)
        if result.returncode != 0:
            continue
        chosen = load_picked(state_path) or set(selected_indexes(result.stdout))
        break

    picked = [r for r in rows if r["index"] in chosen]
    for n, r in enumerate(picked, 1):
        out(f"[{n}/{len(picked)}] {r['label']} {r['title']}")
        path = resolve(r["repo"])
        if path is None:
            if ask(f"No local clone of {r['repo']}. Clone into <work_root>/.chip-repos/? [y/N] ").strip().lower() != "y":
                out(f"Skipped {r['label']}.")
                continue
            try:
                path = clone(r["repo"])
            except Exception as exc:  # CloneError or gh failure: tell and move on
                out(f"Clone failed: {exc}. Skipped {r['label']}.")
                continue
        claude(config.fill_prompt(config.load()["skills"][0], r), path)
        if n < len(picked):
            nxt = picked[n]
            if ask(f"Continue with {nxt['label']}? [Y/n] ").strip().lower() == "n":
                break
    return 0
