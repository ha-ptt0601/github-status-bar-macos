"""Render an inbox as a markdown table for the terminal."""
from __future__ import annotations

from chip import model

STATUS_LABEL = {
    model.REREVIEW: "Re-review",
    model.NEW: "New",
    model.WAITING: "Waiting on author",
    model.COMMENTED: "Commented",
    model.APPROVED: "approved",
}
HEADER = ["#", "Repo", "PR", "Title", "Author", "Waiting", "Status", "Decision", "Size", "CI", "Merge", "Base", "Jira"]
TITLE_WIDTH = 50


def _short(text: str, width: int) -> str:
    return text if len(text) <= width else text[: width - 1] + "…"


def _line(cells) -> str:
    return "| " + " | ".join(str(c).replace("|", "\\|") for c in cells) + " |"


def render_table(inbox: dict) -> str:
    lines = []
    if not inbox["rows"]:
        lines.append("Inbox zero 🎉")
    else:
        lines.append(_line(HEADER))
        lines.append("|" + "---|" * len(HEADER))
        for r in inbox["rows"]:
            lines.append(_line([
                r["index"],
                r["repo"].split("/")[-1],
                f"#{r['number']}",
                _short(r["title"], TITLE_WIDTH),
                r["author"],
                r["wait"],
                STATUS_LABEL[r["status"]],
                r["decision"],
                r["size"],
                r["ci"],
                "conflict" if r["conflict"] else "ok",
                r["base"] + (" (stacked)" if r["stacked"] else ""),
                r["jira"] or "-",
            ]))
    hidden = inbox["hidden"]
    if hidden["approved"] or hidden["draft"]:
        lines.append("")
        lines.append(f"Hidden: {hidden['approved']} approved, {hidden['draft']} drafts — `chip list --all` shows all.")
    return "\n".join(lines)
