"""Turn inbox rows into AskUserQuestion pages (multi-select PR questions + a nav question)."""
from __future__ import annotations

from collections import Counter
from typing import List

from chip.render import STATUS_LABEL

PER_PAGE = 12
PER_QUESTION = 4
REVIEW_NOW = "Review các PR đã chọn"
NEXT_PAGE = "Xem trang tiếp"
SKIP = "Không chọn"


def assign_labels(rows: List[dict]) -> List[dict]:
    """Label each row `repo#N`, or `owner/repo#N` when two owners share a repo name."""
    owners_per_name = Counter(full.split("/")[-1] for full in {r["repo"] for r in rows})
    for r in rows:
        name = r["repo"].split("/")[-1]
        r["label"] = f"{r['repo'] if owners_per_name[name] > 1 else name}#{r['number']}"
    return rows


def _description(r: dict) -> str:
    parts = [r["title"], r["author"], r["wait"], STATUS_LABEL[r["status"]]]
    if r["decision"] != "-":
        parts.append(r["decision"])
    parts += [r["size"], r["base"] + (" (stacked)" if r["stacked"] else "")]
    if r["conflict"]:
        parts.append("conflict")
    if r["jira"]:
        parts.append(r["jira"])
    return " · ".join(parts)


def _chunks(items: List[dict]) -> List[List[dict]]:
    chunks = [items[i:i + PER_QUESTION] for i in range(0, len(items), PER_QUESTION)]
    if len(chunks) > 1 and len(chunks[-1]) == 1:
        chunks[-1].insert(0, chunks[-2].pop())
    return chunks


def build_page(rows: List[dict], page: int) -> dict:
    pages = max(1, -(-len(rows) // PER_PAGE))
    if not 1 <= page <= pages:
        raise ValueError(f"trang {page} ngoài khoảng 1-{pages}")
    start = (page - 1) * PER_PAGE
    questions = []
    offset = start
    for chunk in _chunks(rows[start:start + PER_PAGE]):
        first, last = offset + 1, offset + len(chunk)
        offset = last
        options = [{"label": r["label"], "description": _description(r)} for r in chunk]
        if len(options) == 1:
            options.append({"label": SKIP, "description": "Không review PR nào"})
        questions.append({
            "question": f"Chọn PR để review ({first}–{last} / {len(rows)})",
            "header": f"PR {first}-{last}",
            "multiSelect": True,
            "options": options,
        })
    if page < pages:
        nxt_first, nxt_last = page * PER_PAGE + 1, min(len(rows), (page + 1) * PER_PAGE)
        questions.append({
            "question": "Tiếp theo?",
            "header": f"Trang {page}/{pages}",
            "multiSelect": False,
            "options": [
                {"label": REVIEW_NOW, "description": "Dừng chọn, review các PR đã tick"},
                {"label": NEXT_PAGE, "description": f"PR {nxt_first}–{nxt_last}; lựa chọn ở trang này được giữ"},
            ],
        })
    return {"page": page, "pages": pages, "total": len(rows), "questions": questions}
