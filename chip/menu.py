"""Turn inbox rows into AskUserQuestion pages (multi-select PR questions + a nav question)."""
from __future__ import annotations

from collections import Counter
from typing import Iterable, List

from chip import model
from chip.render import STATUS_LABEL

PER_PAGE = 12
ONE_SCREEN = 16  # 4 questions x 4 options: fits without a nav question
PER_QUESTION = 4
REVIEW_NOW = "Review các PR đã chọn"
NEXT_PAGE = "Xem trang tiếp"
FILTER_REPO = "Đổi project"
SEARCH = "Tìm kiếm"
SKIP = "Không chọn"
ALL_REPOS = "Tất cả"


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


def _repo_description(rs: List[dict]) -> str:
    rereview = sum(1 for r in rs if r["status"] == model.REREVIEW)
    return f"{len(rs)} PR" + (f" · {rereview} {STATUS_LABEL[model.REREVIEW]}" if rereview else "")


def project_question(rows: List[dict]) -> dict:
    """One single-select question: `Tất cả` + the 3 busiest repos; the rest are typed via Other."""
    names = _repo_names(rows)
    counts = Counter(r["repo"] for r in rows)
    ordered = sorted(counts, key=lambda f: (-counts[f], names[f]))
    top, rest = ordered[:PER_QUESTION - 1], ordered[PER_QUESTION - 1:]
    options = [{"label": ALL_REPOS, "description": _repo_description(rows)}]
    for full in top:
        options.append({"label": names[full], "description": _repo_description([r for r in rows if r["repo"] == full])})
    question = "Chọn project"
    if rest:
        question += " — repo khác gõ tên vào ô trống: " + ", ".join(f"{names[f]} ({counts[f]})" for f in rest)
    return {"question": question, "header": "Project", "multiSelect": False, "options": options}


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
    single = len(rows) <= ONE_SCREEN
    per_page = ONE_SCREEN if single else PER_PAGE
    pages = max(1, -(-len(rows) // per_page))
    if not 1 <= page <= pages:
        raise ValueError(f"trang {page} ngoài khoảng 1-{pages}")
    start = (page - 1) * per_page
    questions = []
    offset = start
    for chunk in _chunks(rows[start:start + per_page]):
        first, last = offset + 1, offset + len(chunk)
        offset = last
        options = [{"label": r["label"], "description": _description(r)} for r in chunk]
        if len(options) == 1:
            options.append({"label": SKIP, "description": "Không review PR nào"})
        questions.append({
            "question": f"Chọn PR để review ({first}–{last} / {len(rows)})"
            + (" — Space tick, Tab nhóm kế; ô trống: gõ từ khoá / tên project" if first == start + 1 else ""),
            "header": f"PR {first}-{last}",
            "multiSelect": True,
            "options": options,
        })
    if single:
        return {"page": page, "pages": pages, "total": len(rows), "filter": filter_text, "questions": questions}
    nav = [{"label": REVIEW_NOW, "description": "Dừng chọn, review các PR đã tick"}]
    if page < pages:
        nxt_first, nxt_last = page * PER_PAGE + 1, min(len(rows), (page + 1) * PER_PAGE)
        nav.append({"label": NEXT_PAGE, "description": f"PR {nxt_first}–{nxt_last}; lựa chọn ở trang này được giữ"})
    nav += [
        {"label": FILTER_REPO, "description": "Chọn lại project"},
        {"label": SEARCH, "description": "Theo title, author, Jira, repo — hoặc gõ từ khoá vào Other"},
    ]
    questions.append({
        "question": f"Tiếp theo? (đang lọc: {filter_text})" if filter_text else "Tiếp theo?",
        "header": f"Trang {page}/{pages}",
        "multiSelect": False,
        "options": nav,
    })
    return {"page": page, "pages": pages, "total": len(rows), "filter": filter_text, "questions": questions}
