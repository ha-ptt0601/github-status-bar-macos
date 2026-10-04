"""Act on a PR from the menu: review it (approve, request changes, comment) or manage your own
(merge, close, ready/draft, comment). Each action that changes GitHub asks first in a small dialog."""
from __future__ import annotations

import json
import re
import subprocess
from typing import Callable, List, Optional, Tuple

# name: (who, dialog prompt, button, text: None = no field, "optional" or "required")
ACTIONS = {
    "approve": ("review", "Approve {label}?\n{title}\n\nOptional comment:", "Approve", "optional"),
    "request-changes": ("review", "Request changes on {label}?\n{title}\n\nWhat needs to change:",
                        "Request changes", "required"),
    "comment": ("any", "Comment on {label}\n{title}", "Comment", "required"),
    "merge": ("mine", "Merge {label}?\n{title}", "Merge", None),
    "close": ("mine", "Close {label} without merging?\n{title}", "Close PR", None),
    "ready": ("mine", "", "", None),  # no dialog: reversible
    "draft": ("mine", "", "", None),
}
DONE = {"approve": "Approved", "request-changes": "Requested changes on", "comment": "Commented on",
        "merge": "Merged", "close": "Closed", "ready": "Marked ready for review:", "draft": "Converted to draft:"}
DIALOG_RE = re.compile(r"button returned:([^,]*)(?:, text returned:(.*))?", re.S)


class ActionError(Exception):
    pass


def _quote(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def ask(prompt: str, button: str, text: Optional[str], runner=None) -> Optional[str]:
    """A native dialog. Returns the text typed ("" without a text field), or None on Cancel."""
    runner = runner or subprocess.run
    answer = ' default answer ""' if text else ""
    script = (f'display dialog "{_quote(prompt)}"{answer} with title "GitHubBar" '
              f'buttons {{"Cancel", "{_quote(button)}"}} default button "{_quote(button)}" cancel button "Cancel"')
    while True:
        proc = runner(["osascript", "-e", script], capture_output=True, text=True)
        match = DIALOG_RE.search(proc.stdout or "")
        if proc.returncode != 0 or not match or match.group(1) != button:
            return None
        typed = (match.group(2) or "").strip()
        if text == "required" and not typed:
            continue  # ask again: this action needs a message
        return typed


def merge_flag(repo: str, runner=None) -> str:
    """The repo's preferred merge method: squash if allowed, else a merge commit, else rebase."""
    runner = runner or subprocess.run
    proc = runner(["gh", "api", f"repos/{repo}", "--jq",
                   "[.allow_squash_merge, .allow_merge_commit, .allow_rebase_merge]"],
                  capture_output=True, text=True)
    try:
        squash, merge, rebase = json.loads(proc.stdout)
    except (ValueError, TypeError):
        return "--merge"
    return "--squash" if squash else "--merge" if merge else "--rebase" if rebase else "--merge"


def command(action: str, row: dict, body: str, runner=None) -> List[str]:
    url, mine = row["url"], row.get("kind") == "mine"
    if action == "approve":
        return ["gh", "pr", "review", url, "--approve"] + (["--body", body] if body else [])
    if action == "request-changes":
        return ["gh", "pr", "review", url, "--request-changes", "--body", body]
    if action == "comment":
        return (["gh", "pr", "comment", url, "--body", body] if mine
                else ["gh", "pr", "review", url, "--comment", "--body", body])
    if action == "merge":
        return ["gh", "pr", "merge", url, merge_flag(row["repo"], runner)]
    if action == "close":
        return ["gh", "pr", "close", url]
    if action == "ready":
        return ["gh", "pr", "ready", url]
    if action == "draft":
        return ["gh", "pr", "ready", url, "--undo"]
    raise ActionError(f"unknown action {action}")


def run(action: str, row: dict, runner=None, dialog: Callable = ask) -> Tuple[bool, str]:
    """Ask (when the action changes GitHub), then run it. (False, "") means the user cancelled."""
    if action not in ACTIONS:
        raise ActionError(f"unknown action {action}")
    who, prompt, button, text = ACTIONS[action]
    mine = row.get("kind") == "mine"
    if (who == "mine" and not mine) or (who == "review" and mine):
        raise ActionError(f"{action} is not available on {row['label']}")
    body = ""
    if prompt:
        body = dialog(prompt.format(label=row["label"], title=row["title"]), button, text)
        if body is None:
            return False, ""
    runner = runner or subprocess.run
    proc = runner(command(action, row, body, runner), capture_output=True, text=True)
    if proc.returncode != 0:
        raise ActionError((proc.stderr or proc.stdout or f"gh failed ({action})").strip())
    return True, f"{DONE[action]} {row['label']}"
