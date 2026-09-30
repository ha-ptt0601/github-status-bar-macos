"""`chip` with no subcommand: an fzf picker (like Claude Code's prompt search) that opens claude per PR."""
from __future__ import annotations

import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Callable, List, Optional

from chip import model
from chip.render import STATUS_LABEL

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
STATUS_COLOR = {
    model.REREVIEW: "33",   # yellow
    model.NEW: "32",        # green
    model.WAITING: "90",    # grey
    model.COMMENTED: "90",
    model.APPROVED: "36",   # cyan
}
LABEL_WIDTH = 30
BIN = Path(__file__).resolve().parents[1] / "bin" / "chip"
REVIEW_PROMPT = "/my-review-skill {url}"


def _c(code: str, text: str) -> str:
    return f"\x1b[{code}m{text}\x1b[0m"


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def fzf_lines(inbox: dict) -> List[str]:
    """One line per row: hidden `index<TAB>` then the coloured, searchable columns."""
    lines = []
    for r in inbox["rows"]:
        status = STATUS_LABEL[r["status"]]
        extra = "  ".join(x for x in (r["jira"], "conflict" if r["conflict"] else "") if x)
        lines.append("\t".join([
            str(r["index"]),
            f"{_c('90', r['wait'].rjust(5))}  {r['label'].ljust(LABEL_WIDTH)} "
            f"{_c(STATUS_COLOR[r['status']], status.ljust(13))} {r['title']}  {_c('90', '· ' + r['author'])}"
            + (f"  {_c('35', extra)}" if extra else ""),
        ]))
    return lines


def preview_text(r: dict) -> str:
    base = r["base"] + (" (stacked)" if r["stacked"] else "")
    fields = [
        ("Trạng thái", STATUS_LABEL[r["status"]]),
        ("Author", r["author"]),
        ("Chờ", r["wait"]),
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


def run_fzf(lines: List[str], header: str) -> subprocess.CompletedProcess:
    preview = f"{shlex.quote(sys.executable)} {shlex.quote(str(BIN))} preview {{1}}"
    cmd = [
        # --exact + --no-sort: substring search (space = AND) that keeps the inbox priority order
        "fzf", "--multi", "--ansi", "--exact", "--no-sort", "--delimiter=\t", "--with-nth=2..",
        "--border=rounded", "--border-label= chip · PR chờ review ", "--border-label-pos=3",
        "--prompt=⌕ ", "--pointer=❯", "--marker=◉", "--info=inline-right",
        f"--header={header}", "--header-first",
        f"--preview={preview}", "--preview-window=right,40%,wrap,border-rounded",
    ]
    return subprocess.run(cmd, input="\n".join(lines), stdout=subprocess.PIPE, text=True)


def run_claude(prompt: str, cwd: str) -> None:
    subprocess.run(["claude", prompt], cwd=cwd)


def run_ui(
    inbox: dict,
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
    header = (f"{len(rows)} PR · ẩn {hidden['approved']} đã approve, {hidden['draft']} draft"
              "   Tab tick · Enter review · Esc thoát")
    result = fzf(fzf_lines(inbox), header)
    if result.returncode != 0:
        return 0
    picked = [rows[i - 1] for i in selected_indexes(result.stdout)]
    for n, r in enumerate(picked, 1):
        out(f"[{n}/{len(picked)}] {r['label']} {r['title']}")
        path = resolve(r["repo"])
        if path is None:
            if ask(f"Chưa có clone local của {r['repo']}. Clone vào ~/work/.chip-repos/? [y/N] ").strip().lower() != "y":
                out(f"Bỏ qua {r['label']}.")
                continue
            try:
                path = clone(r["repo"])
            except Exception as exc:  # CloneError or gh failure: tell and move on
                out(f"Clone thất bại: {exc}. Bỏ qua {r['label']}.")
                continue
        claude(REVIEW_PROMPT.format(url=r["url"]), path)
        if n < len(picked):
            nxt = picked[n]
            if ask(f"Tiếp {nxt['label']}? [Y/n] ").strip().lower() == "n":
                break
    return 0
