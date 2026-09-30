"""Render an inbox as a markdown table for the terminal."""
from __future__ import annotations

from chip import model

STATUS_LABEL = {
    model.REREVIEW: "cần re-review",
    model.NEW: "mới",
    model.WAITING: "chờ author",
    model.COMMENTED: "đã comment",
    model.APPROVED: "đã approve",
}
HEADER = ["#", "Repo", "PR", "Title", "Author", "Chờ", "Trạng thái", "Decision", "Size", "CI", "Merge", "Base", "Jira"]
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
        lines.append(f"Ẩn: {hidden['approved']} đã approve, {hidden['draft']} draft — `chip list --all` để xem hết.")
    return "\n".join(lines)
