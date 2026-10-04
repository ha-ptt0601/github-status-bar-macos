"""`chip` (fzf picker) and `chip menu | repos | list | pick | repo | preview` for the /chip skill."""
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from chip import config, fetch, installer, mcp_server, menu, model, notify, render, repos, runs, store, terminal, tui, updates
from chip.selection import SelectionError, parse_selection

AUTH_HINT = "gh does not seem to be logged in — run `! gh auth login` and try again."
PICK_FIELDS = ("index", "label", "repo", "number", "title", "url")
CACHE_TTL_SECONDS = store.CACHE_TTL_SECONDS


def cache_dir() -> Path:
    return store.cache_dir()


def work_root() -> Path:
    return store.work_root()


def _error(message: str) -> None:
    print(f"chip: {message}", file=sys.stderr)


def _refresh(show_all: bool, runner, force: bool = False) -> Optional[dict]:
    """Visible view of the cached/fetched inbox; None (error already printed) on failure."""
    inbox, error = store.load_all(runner, force)
    if error:
        _error(error)
        if "auth" in error.lower() or "401" in error:
            print(AUTH_HINT, file=sys.stderr)
        return None
    return model.visible_view(inbox, show_all)


def _cached_inbox(show_all: bool = False) -> Optional[dict]:
    inbox = store.cached_all()
    if inbox is None or not inbox.get("all_rows"):
        _error("no list yet — run `chip menu` first.")
        return None
    return model.visible_view(inbox, show_all)


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
        _error(f"no PR number {args.index}")
        return 2
    print(tui.preview_text(rows[args.index - 1]))
    return 0


def cmd_ui(runner) -> int:
    print("Loading PRs from GitHub…", file=sys.stderr)
    inbox = _refresh(False, runner)
    if inbox is None:
        return 1
    cache = cache_dir() / "repos.json"
    return tui.run_ui(
        inbox,
        cache_dir() / "picked.json",
        resolve=lambda slug: repos.resolve(slug, work_root(), cache),
        clone=lambda slug: repos.clone(slug, work_root(), cache),
    )


def cmd_open() -> int:
    """Open the fzf picker in a new terminal window (skills cannot draw a TUI inside Claude Code)."""
    app = terminal.pick_app(config.load()["terminal"])
    ok, message = terminal.open_command(str(tui.BIN), app)
    if not ok:
        _error(message or "osascript failed")
        return 1
    print(f"Opened chip in a new {app} window.")
    return 0


def cmd_internal(args) -> int:
    """Callbacks for the fzf picker: `_toggle N`, `_prs REPO`, `_repo-preview REPO`."""
    inbox = _cached_inbox()
    if inbox is None:
        return 2
    picked_path = cache_dir() / "picked.json"
    if args.cmd == "_toggle":
        tui.toggle_picked(picked_path, int(args.arg))
    elif args.cmd == "_prs":
        print("\n".join(tui.pr_lines(inbox, args.arg, tui.load_picked(picked_path))))
    else:
        print(tui.repo_preview(inbox, args.arg))
    return 0


def cmd_mcp(runner) -> int:
    """Serve PRs as MCP resources; first refresh reuses a recent fetch, later ones always refetch."""
    cached = store.cached_all()
    initial = model.visible_view(cached) if cached and cached.get("all_rows") else {"rows": [], "hidden": {"approved": 0, "draft": 0}}
    calls = {"n": 0}

    def refresh():
        calls["n"] += 1
        return _refresh(False, runner, force=calls["n"] > 1)

    mcp_server.serve(initial, refresh)
    return 0


def cmd_repos(args, runner) -> int:
    if args.refresh:
        inbox = _refresh(args.all, runner, force=args.force)
        if inbox is None:
            return 1
    else:
        inbox = _cached_inbox()
        if inbox is None:
            return 2
    out = {
        "total": len(inbox["rows"]),
        "hidden": inbox["hidden"],
        "fetched_at": inbox.get("fetched_at"),
        "updated": datetime.fromtimestamp(inbox.get("fetched_at", time.time())).strftime("%H:%M"),
        "questions": [menu.project_question(inbox["rows"])],
    }
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


def cmd_pick(args) -> int:
    inbox = _cached_inbox()
    if inbox is None:
        return 2
    rows = inbox["rows"]
    selection = args.selection
    if "pr://" in selection:  # `@chip:pr://repo/N-slug` mentions typed in the prompt bar
        selection = ",".join(mcp_server.labels_in(selection))
    try:
        picked = parse_selection(selection, len(rows), [r.get("label", "") for r in rows])
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
            _error(f"no local clone of {args.slug} under {work_root()}")
            return 2
    print(path)
    return 0


def _find_row(label: str) -> Optional[dict]:
    """Row (approved/drafts included) by label from the cached inbox."""
    inbox = store.cached_all() or {}
    return next((r for r in inbox.get("rows", []) if r.get("label") == label), None)


def _skill(cfg: dict, number: int) -> Optional[dict]:
    skills = cfg["skills"]
    if not 1 <= number <= len(skills):
        _error(f"no skill {number} (config has {len(skills)})")
        return None
    return skills[number - 1]


def cmd_config(args) -> int:
    path = config.config_path()
    if args.action == "path":
        print(path)
        return 0
    if args.action == "set":
        if not (args.key and args.value):
            _error("usage: chip config set <key> <value>")
            return 2
        errors = config.set_value(args.key, args.value, path)
        for message in errors:
            _error(message)
        return 2 if errors else 0
    if args.action in ("init", "open"):
        created = config.init(path)
        if args.action == "init":
            print(f"{'created' if created else 'exists'} {path}")
            return 0
        subprocess.run(["open", "-e", str(path)])
        return 0
    cfg = config.load(path)
    if cfg["errors"]:
        for message in cfg["errors"]:
            _error(message)
        return 1
    print(json.dumps({k: v for k, v in cfg.items() if k != "errors"}, ensure_ascii=False, indent=1))
    return 0


def cmd_prompt(args) -> int:
    row = _find_row(args.label)
    if row is None:
        _error(f"PR {args.label} is not in the list")
        return 2
    skill = _skill(config.load(), args.skill)
    if skill is None:
        return 2
    print(config.fill_prompt(skill, row))
    return 0


def _runs_path() -> Path:
    return cache_dir() / "runs.json"


def cmd_run(args, runner) -> int:
    cfg = config.load()
    skill = _skill(cfg, args.skill)
    if skill is None:
        return 2
    row = _find_row(args.label)
    if row is None and _refresh(True, runner, force=True) is not None:
        row = _find_row(args.label)
    if row is None:
        notify.send([f"{args.label} is no longer waiting for your review"])
        _error(f"PR {args.label} is not in the list")
        return 1
    cache = cache_dir() / "repos.json"
    try:
        path = repos.resolve(row["repo"], work_root(), cache) or repos.clone(row["repo"], work_root(), cache)
        record = runs.start(row, skill, cfg, path, _runs_path())
    except (repos.CloneError, runs.RunError) as exc:
        notify.send([f"Could not start review for {args.label}: {exc}"])
        _error(str(exc))
        return 1
    notify.send([f"Reviewing {row['label']} ({skill['name']})"])
    print(f"started {record['id']} for {row['label']} ({skill['name']})")
    return 0


def _known_run(run_id: str) -> bool:
    if runs.find_by_id(runs.load(_runs_path()), run_id) is None:
        _error(f"no chip run {run_id}")
        return False
    return True


def cmd_attach(args) -> int:
    if not _known_run(args.id):
        return 2
    ok, message = terminal.open_command(f"claude attach {args.id}", terminal.pick_app(config.load()["terminal"]))
    if not ok:
        _error(message or "osascript failed")
        return 1
    return 0


def cmd_stop(args) -> int:
    if not _known_run(args.id):
        return 2
    subprocess.run(["claude", "stop", args.id], capture_output=True, text=True)
    return 0


def cmd_forget(args) -> int:
    records = runs.load(_runs_path())
    found = runs.find_by_id(records, args.id)
    if found is None:
        _error(f"no chip run {args.id}")
        return 2
    subprocess.run(["claude", "rm", args.id], capture_output=True, text=True)
    del records[found[0]]
    runs.save(_runs_path(), records)
    return 0


def cmd_copy(args) -> int:
    row = _find_row(args.label)
    if row is None:
        _error(f"PR {args.label} is not in the list")
        return 2
    subprocess.run(["pbcopy"], input=row["url"], text=True)
    return 0


def cmd_swiftbar(args, runner) -> int:
    from chip import swiftbar
    plugin = os.environ.get("CHIP_PLUGIN") or str(tui.BIN)
    print(swiftbar.build_menu(plugin, force=args.force, fetch_runner=runner))
    return 0


def cmd_update(args) -> int:
    if args.check:
        latest = updates.latest_release(cache_dir() / "update.json", now=time.time(), force=True)
        print(latest or "no release found")
        return 0
    repo = installer.REPO_DIR
    ok, message = updates.update_repo(str(repo))
    if not ok:
        command = f"cd {shlex.quote(str(repo))} && git status && echo {shlex.quote('chip update stopped: ' + message)}"
        terminal.open_command(command, terminal.pick_app(config.load()["terminal"]))
        notify.send([f"chip update stopped: {message}"])
        return 1
    installer.install(repo)
    notify.send([f"chip updated to v{updates.read_version(repo)}"])
    return 0


def main(argv=None, runner=None) -> int:
    parser = argparse.ArgumentParser(prog="chip", description="PR review inbox")
    sub = parser.add_subparsers(dest="cmd")
    p_list = sub.add_parser("list", help="table of PRs waiting for your review")
    p_list.add_argument("--all", action="store_true", help="include approved PRs and drafts")
    p_menu = sub.add_parser("menu", help="AskUserQuestion page (JSON); fetches unless --page/--cached")
    p_menu.add_argument("--page", type=int, help="page N of the last fetch, no GitHub call")
    p_menu.add_argument("--all", action="store_true", help="include approved PRs and drafts")
    p_menu.add_argument("--cached", action="store_true", help="use the last fetch, no GitHub call")
    p_menu.add_argument("--repo", help="only these repos (short or owner/repo), comma-separated")
    p_menu.add_argument("--q", help="keywords: title, author, Jira, repo, base (all words must match)")
    p_repos = sub.add_parser("repos", help="AskUserQuestion project question (JSON)")
    p_repos.add_argument("--refresh", action="store_true", help="refetch from GitHub first")
    p_repos.add_argument("--all", action="store_true", help="include approved PRs and drafts")
    p_repos.add_argument("--force", action="store_true", help="ignore a fetch from the last 3 minutes")
    for name in ("_toggle", "_prs", "_repo-preview"):
        sub.add_parser(name).add_argument("arg")
    sub.add_parser("mcp", help="MCP server (stdio): each PR is a resource for @-mentions")
    sub.add_parser("open", help="open the `chip` picker in a new terminal window")
    p_preview = sub.add_parser("preview", help="details of PR number N (fzf preview)")
    p_preview.add_argument("index", type=int)
    p_pick = sub.add_parser("pick", help="pick PRs from the last list: repo#N | 1,3 | 2-4 | all")
    p_pick.add_argument("selection")
    p_repo = sub.add_parser("repo", help="local clone path of owner/repo")
    p_repo.add_argument("slug")
    p_repo.add_argument("--clone", action="store_true", help="clone into <work_root>/.chip-repos if missing")
    p_config = sub.add_parser("config", help="config file: init | check | path | open | set KEY VALUE")
    p_config.add_argument("action", choices=["init", "check", "path", "open", "set"])
    p_config.add_argument("key", nargs="?")
    p_config.add_argument("value", nargs="?")
    p_prompt = sub.add_parser("prompt", help="review prompt for a PR label from the configured skill")
    p_prompt.add_argument("label")
    p_prompt.add_argument("--skill", type=int, default=1)
    p_run = sub.add_parser("run", help="start a background review for a PR label")
    p_run.add_argument("label")
    p_run.add_argument("--skill", type=int, default=1)
    for name in ("attach", "stop", "forget"):
        sub.add_parser(name, help=f"{name} a chip review by session id").add_argument("id")
    sub.add_parser("copy", help="copy a PR link").add_argument("label")
    p_swiftbar = sub.add_parser("swiftbar", help="print the SwiftBar menu (used by the menu bar plugin)")
    p_swiftbar.add_argument("--force", action="store_true", help="refetch from GitHub now")
    sub.add_parser("install", help="link chip, install the /chip skill, MCP server and menu bar plugin")
    sub.add_parser("uninstall", help="remove what `chip install` added")
    p_update = sub.add_parser("update", help="pull the latest chip and reinstall")
    p_update.add_argument("--check", action="store_true", help="only check GitHub for a newer release")
    args = parser.parse_args(argv)

    if args.cmd is None:
        return cmd_ui(runner or fetch.run_gh_graphql)
    if args.cmd in ("_toggle", "_prs", "_repo-preview"):
        return cmd_internal(args)
    if args.cmd == "mcp":
        return cmd_mcp(runner or fetch.run_gh_graphql)
    if args.cmd == "open":
        return cmd_open()
    if args.cmd == "preview":
        return cmd_preview(args)
    if args.cmd == "install":
        return installer.install()
    if args.cmd == "uninstall":
        return installer.uninstall()
    if args.cmd == "update":
        return cmd_update(args)
    if args.cmd == "swiftbar":
        return cmd_swiftbar(args, runner or fetch.run_gh_graphql)
    if args.cmd == "run":
        return cmd_run(args, runner or fetch.run_gh_graphql)
    if args.cmd == "attach":
        return cmd_attach(args)
    if args.cmd == "stop":
        return cmd_stop(args)
    if args.cmd == "forget":
        return cmd_forget(args)
    if args.cmd == "copy":
        return cmd_copy(args)
    if args.cmd == "config":
        return cmd_config(args)
    if args.cmd == "prompt":
        return cmd_prompt(args)
    if args.cmd == "list":
        return cmd_list(args, runner or fetch.run_gh_graphql)
    if args.cmd == "menu":
        return cmd_menu(args, runner or fetch.run_gh_graphql)
    if args.cmd == "repos":
        return cmd_repos(args, runner or fetch.run_gh_graphql)
    if args.cmd == "pick":
        return cmd_pick(args)
    return cmd_repo(args)
