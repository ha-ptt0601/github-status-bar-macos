"""`chip` (fzf picker) and `chip menu | repos | list | pick | repo | preview` for the /chip skill."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from chip import fetch, menu, model, render, repos, tui
from chip.selection import SelectionError, parse_selection

AUTH_HINT = "Có vẻ gh chưa đăng nhập — chạy `! gh auth login` rồi thử lại."
PICK_FIELDS = ("index", "label", "repo", "number", "title", "url")


def cache_dir() -> Path:
    return Path(os.environ.get("CHIP_CACHE_DIR") or Path.home() / ".cache" / "chip")


def work_root() -> Path:
    return Path(os.environ.get("CHIP_WORK_ROOT") or Path.home() / "work")


def _error(message: str) -> None:
    print(f"chip: {message}", file=sys.stderr)


def _refresh(show_all: bool, runner) -> Optional[dict]:
    """Fetch, build and cache the inbox; None (error already printed) on failure."""
    try:
        viewer, nodes = fetch.fetch_inbox_nodes(runner)
    except fetch.FetchError as exc:
        _error(str(exc))
        if "auth" in str(exc).lower() or "401" in str(exc):
            print(AUTH_HINT, file=sys.stderr)
        return None
    inbox = model.build_inbox(nodes, viewer, datetime.now(timezone.utc), show_all=show_all)
    menu.assign_labels(inbox["rows"])
    cache_dir().mkdir(parents=True, exist_ok=True)
    (cache_dir() / "last.json").write_text(json.dumps(inbox, ensure_ascii=False, indent=1))
    return inbox


def _cached_inbox() -> Optional[dict]:
    last = cache_dir() / "last.json"
    if not last.exists():
        _error("chưa có danh sách — chạy `chip menu` trước.")
        return None
    return json.loads(last.read_text())


def cmd_list(args, runner) -> int:
    inbox = _refresh(args.all, runner)
    if inbox is None:
        return 1
    print(render.render_table(inbox))
    return 0


def cmd_menu(args, runner) -> int:
    if args.cached or args.page is not None:
        inbox = _cached_inbox()
        if inbox is None:
            return 2
    else:
        inbox = _refresh(args.all, runner)
        if inbox is None:
            return 1
    repo_filter = [r for r in (args.repo or "").split(",") if r.strip()]
    rows = menu.filter_rows(inbox["rows"], repos=repo_filter, query=args.q or "")
    filter_text = " · ".join(
        part for part in (
            f"repo={','.join(repo_filter)}" if repo_filter else "",
            f"q={args.q}" if args.q else "",
        ) if part
    )
    if not rows:
        page = {"page": 0, "pages": 0, "total": 0, "filter": filter_text, "questions": []}
    else:
        try:
            page = menu.build_page(rows, args.page or 1, filter_text)
        except ValueError as exc:
            _error(str(exc))
            return 2
    page["hidden"] = inbox["hidden"]
    print(json.dumps(page, ensure_ascii=False, indent=1))
    return 0


def cmd_preview(args) -> int:
    inbox = _cached_inbox()
    if inbox is None:
        return 2
    rows = inbox["rows"]
    if not 1 <= args.index <= len(rows):
        _error(f"không có PR số {args.index}")
        return 2
    print(tui.preview_text(rows[args.index - 1]))
    return 0


def cmd_ui(runner) -> int:
    print("Đang tải PR từ GitHub…", file=sys.stderr)
    inbox = _refresh(False, runner)
    if inbox is None:
        return 1
    cache = cache_dir() / "repos.json"
    return tui.run_ui(
        inbox,
        resolve=lambda slug: repos.resolve(slug, work_root(), cache),
        clone=lambda slug: repos.clone(slug, work_root(), cache),
    )


def cmd_repos() -> int:
    inbox = _cached_inbox()
    if inbox is None:
        return 2
    print(json.dumps({"questions": menu.repo_questions(inbox["rows"])}, ensure_ascii=False, indent=1))
    return 0


def cmd_pick(args) -> int:
    inbox = _cached_inbox()
    if inbox is None:
        return 2
    rows = inbox["rows"]
    try:
        picked = parse_selection(args.selection, len(rows), [r.get("label", "") for r in rows])
    except SelectionError as exc:
        _error(str(exc))
        return 2
    out = [{k: rows[i - 1].get(k) for k in PICK_FIELDS} for i in picked]
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


def cmd_repo(args) -> int:
    cache = cache_dir() / "repos.json"
    if args.clone:
        try:
            path = repos.clone(args.slug, work_root(), cache)
        except repos.CloneError as exc:
            _error(str(exc))
            return 1
    else:
        path = repos.resolve(args.slug, work_root(), cache)
        if path is None:
            _error(f"không tìm thấy clone local của {args.slug} trong {work_root()}")
            return 2
    print(path)
    return 0


def main(argv=None, runner=None) -> int:
    parser = argparse.ArgumentParser(prog="chip", description="PR review inbox")
    sub = parser.add_subparsers(dest="cmd")
    p_list = sub.add_parser("list", help="bảng PR đang chờ bạn review")
    p_list.add_argument("--all", action="store_true", help="hiện cả PR đã approve và draft")
    p_menu = sub.add_parser("menu", help="trang câu hỏi AskUserQuestion (JSON); không có --page thì tải lại")
    p_menu.add_argument("--page", type=int, help="trang N từ danh sách đã tải, không gọi GitHub")
    p_menu.add_argument("--all", action="store_true", help="hiện cả PR đã approve và draft")
    p_menu.add_argument("--cached", action="store_true", help="dùng danh sách đã tải, không gọi GitHub")
    p_menu.add_argument("--repo", help="chỉ repo này (tên ngắn hoặc owner/repo), nhiều repo cách nhau dấu phẩy")
    p_menu.add_argument("--q", help="từ khoá: title, author, Jira, repo, base (mọi từ phải khớp)")
    sub.add_parser("repos", help="câu hỏi AskUserQuestion chọn repo để lọc (JSON)")
    p_preview = sub.add_parser("preview", help="chi tiết PR số N từ danh sách gần nhất (khung preview của fzf)")
    p_preview.add_argument("index", type=int)
    p_pick = sub.add_parser("pick", help="chọn PR từ danh sách gần nhất: repo#N | 1,3 | 2-4 | all")
    p_pick.add_argument("selection")
    p_repo = sub.add_parser("repo", help="đường dẫn clone local của owner/repo")
    p_repo.add_argument("slug")
    p_repo.add_argument("--clone", action="store_true", help="clone vào ~/work/.chip-repos nếu chưa có")
    args = parser.parse_args(argv)

    if args.cmd is None:
        return cmd_ui(runner or fetch.run_gh_graphql)
    if args.cmd == "preview":
        return cmd_preview(args)
    if args.cmd == "list":
        return cmd_list(args, runner or fetch.run_gh_graphql)
    if args.cmd == "menu":
        return cmd_menu(args, runner or fetch.run_gh_graphql)
    if args.cmd == "repos":
        return cmd_repos()
    if args.cmd == "pick":
        return cmd_pick(args)
    return cmd_repo(args)
