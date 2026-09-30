"""Turn inbox rows into AskUserQuestion pages (multi-select PR questions + a nav question)."""
from __future__ import annotations

from collections import Counter
from typing import Iterable, List

from chip import model
from chip.render import STATUS_LABEL

PER_PAGE = 12
PER_QUESTION = 4
REVIEW_NOW = "Review các PR đã chọn"
NEXT_PAGE = "Xem trang tiếp"
FILTER_REPO = "Lọc theo repo"
SEARCH = "Tìm kiếm"
SKIP = "Không chọn"


def _repo_names(rows: List[dict]) -> dict:
    """Full repo name -> display name: the short name unless two owners share it."""
    fulls = {r["repo"] for r in rows}
    owners_per_name = Counter(full.split("/")[-1] for full in fulls)
    return {full: full if owners_per_name[full.split("/")[-1]] > 1 else full.split("/")[-1] for full in fulls}


def assign_labels(rows: List[dict]) -> List[dict]:
    """Label each row `repo#N`, or `owner/repo#N` when two owners share a repo name."""
    names = _repo_names(rows)
    for r in rows:
        r["label"] = f"{names[r['repo']]}#{r['number']}"
    return rows


def filter_rows(rows: List[dict], repos: Iterable[str] = (), query: str = "") -> List[dict]:
    """Keep rows in any of `repos` (short or full name) whose text contains every word of `query`."""
    wanted = {r.strip().lower() for r in repos if r.strip()}
    words = query.lower().split()
    kept = []
    for r in rows:
        if wanted and not {r["repo"].lower(), r["repo"].split("/")[-1].lower()} & wanted:
            continue
        haystack = " ".join([r["label"], r["repo"], r["title"], r["author"], r["jira"], r["base"]]).lower()
        if all(w in haystack for w in words):
            kept.append(r)
    return kept


def repo_questions(rows: List[dict]) -> List[dict]:
    """Multi-select questions listing each repo with its PR count, busiest first."""
    names = _repo_names(rows)
    counts = Counter(r["repo"] for r in rows)
    rereview = Counter(r["repo"] for r in rows if r["status"] == model.REREVIEW)
    options = []
    for full in sorted(counts, key=lambda f: (-counts[f], names[f])):
        description = f"{counts[full]} PR"
        if rereview[full]:
            description += f" · {rereview[full]} {STATUS_LABEL[model.REREVIEW]}"
        options.append({"label": names[full], "description": description})
    if len(options) == 1:
        options.append({"label": SKIP, "description": "Không lọc"})
    return [
        {"question": "Lọc theo repo (chọn nhiều)", "header": f"Repo {i + 1}", "multiSelect": True, "options": chunk}
        for i, chunk in enumerate(_chunks(options)[:4])
    ]


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


def build_page(rows: List[dict], page: int, filter_text: str = "") -> dict:
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
    nav = [{"label": REVIEW_NOW, "description": "Dừng chọn, review các PR đã tick"}]
    if page < pages:
        nxt_first, nxt_last = page * PER_PAGE + 1, min(len(rows), (page + 1) * PER_PAGE)
        nav.append({"label": NEXT_PAGE, "description": f"PR {nxt_first}–{nxt_last}; lựa chọn ở trang này được giữ"})
    nav += [
        {"label": FILTER_REPO, "description": "Chỉ hiện PR của các repo bạn chọn"},
        {"label": SEARCH, "description": "Theo title, author, Jira, repo — hoặc gõ từ khoá vào Other"},
    ]
    questions.append({
        "question": f"Tiếp theo? (đang lọc: {filter_text})" if filter_text else "Tiếp theo?",
        "header": f"Trang {page}/{pages}",
        "multiSelect": False,
        "options": nav,
    })
    return {"page": page, "pages": pages, "total": len(rows), "filter": filter_text, "questions": questions}
