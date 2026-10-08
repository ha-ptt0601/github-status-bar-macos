"""`chip` (fzf picker) and `chip menu | repos | list | pick | repo | preview` for the /chip skill."""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from chip import (__version__, actions, config, fetch, sessions, installer, mcp_server, menu, model, notify, project, render, repos, runs, store,
                  terminal, tui, updates)
from chip.selection import SelectionError, parse_selection

AUTH_HINT = "gh does not seem to be logged in — run `! gh auth login` and try again."
PICK_FIELDS = ("index", "label", "repo", "number", "title", "url")
CACHE_TTL_SECONDS = store.CACHE_TTL_SECONDS


def cache_dir() -> Path:
    return store.cache_dir()


def find_clone(slug: str) -> Optional[str]:
    return repos.resolve(slug, store.work_roots(), cache_dir() / "repos.json", store.clone_root())


def clone_repo(slug: str) -> str:
    return repos.clone(slug, store.clone_root(), cache_dir() / "repos.json")


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
    return tui.run_ui(
        inbox,
        cache_dir() / "picked.json",
        resolve=find_clone,
        clone=clone_repo,
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
    if args.clone:
        try:
            path = clone_repo(args.slug)
        except repos.CloneError as exc:
            _error(str(exc))
            return 1
    else:
        path = find_clone(args.slug)
        if path is None:
            _error(f"no local clone of {args.slug} under {', '.join(map(str, store.work_roots())) or 'any code folder'}")
            return 2
    print(path)
    return 0


def _find_row(label: str) -> Optional[dict]:
    """Row by label from the cached inbox: PRs to review (approved/drafts included) and the user's own PRs."""
    inbox = store.cached_all() or {}
    return next((r for r in inbox.get("rows", []) + inbox.get("mine", []) if r.get("label") == label), None)


def _skill(skills: list, number: int) -> Optional[dict]:
    if not 1 <= number <= len(skills):
        _error(f"no skill {number} (config has {len(skills)})")
        return None
    return skills[number - 1]


def cmd_config(args) -> int:
    path = config.config_path()
    if args.action == "path":
        print(path)
        return 0
    if args.action == "example":
        print(json.dumps(config.example(), ensure_ascii=False, indent=2))
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
    skill = _skill(config.review_skills(config.load()), args.skill)
    if skill is None:
        return 2
    print(config.fill_prompt(skill, row))
    return 0


def _runs_path() -> Path:
    return cache_dir() / "runs.json"


def cmd_run(args, runner) -> int:
    cfg = config.load()
    if args.project:
        skill = config.DEFAULT_SKILL  # replaced by the repo's own skill once the clone is known
    else:
        skill = _skill(cfg["address_skills"] if args.address else config.review_skills(cfg), args.skill)
    if skill is None:
        return 2
    row = _find_row(args.label)
    if row is None and _refresh(True, runner, force=True) is not None:
        row = _find_row(args.label)
    if row is None:
        notify.send([f"{args.label} is no longer waiting for your review"])
        _error(f"PR {args.label} is not in the list")
        return 1
    if args.feature:
        return _run_in_feature_session(row, skill, cfg)
    try:
        clone = find_clone(row["repo"]) or _first_clone(row["repo"], cfg)
        extra = {}
        if args.project:
            skill, extra = _project_skill(clone), {"auto": True}
        worktree = project.checkout(clone, row, store.worktree_root(), links=cfg["worktree_links"])
        extra.update(clone=clone, worktree=worktree)
        record = runs.start(row, project.in_worktree(skill), cfg, worktree, _runs_path(), address=args.address,
                            extra=extra)
    except (repos.CloneError, runs.RunError, project.WorktreeError) as exc:
        notify.send([f"Could not start review for {args.label}: {exc}"])
        _error(str(exc))
        return 1
    notify.send([f"Reviewing {row['label']} ({skill['name']})"])
    print(f"started {record['id']} for {row['label']} ({skill['name']})")
    return 0


FEATURE_SKILL = "Address review (feature session)"


def feature_session(row: dict) -> Optional[dict]:
    """The session linked to this PR, else the one that opened it, else the one found on its branch."""
    links = sessions.load_links(cache_dir() / "links.json")
    if row["label"] in links:
        return links[row["label"]]
    index = sessions.update_index(cache_dir() / "sessions.json", budget=5)
    clones = repos._load(cache_dir() / "repos.json")
    return sessions.for_rows([row], index, {}, clones).get(row["label"])


def _run_in_feature_session(row: dict, skill: dict, cfg: dict) -> int:
    """Address review inside the session where the feature was built (it remembers the work)."""
    session = feature_session(row)
    if session is None:
        notify.send([f"No feature session for {row['label']}: use Link feature session…"])
        _error(f"no Claude Code session found on branch {row.get('head') or '?'}; link one with chip session link")
        return 1
    try:
        record = runs.start(row, dict(skill, name=FEATURE_SKILL), cfg, session["cwd"], _runs_path(), address=True,
                            resume=session["id"], extra={"feature_session": session["id"]})
    except runs.RunError as exc:
        notify.send([f"Could not start {FEATURE_SKILL} for {row['label']}: {exc}"])
        _error(str(exc))
        return 1
    notify.send([f"Addressing review on {row['label']} in its feature session"])
    print(f"started {record['id']} for {row['label']} ({FEATURE_SKILL})")
    return 0


def cmd_session(args) -> int:
    """open / link / unlink the Claude Code session where one of your PRs was built."""
    row = _find_row(args.label)
    if row is None or row.get("kind") != "mine":
        _error(f"{args.label} is not one of your open PRs")
        return 2
    links_path = cache_dir() / "links.json"
    if args.action == "unlink":
        sessions.unlink(links_path, row["label"])
        return 0
    if args.action == "link":
        session_id = args.id or actions.ask(
            f"Session id for {row['label']}\n{row['title']}\n\nFrom `claude --resume` or "
            "~/.claude/projects/<folder>/<session-id>.jsonl:", "Link", "required")
        if not session_id:
            return 0
        index = sessions.update_index(cache_dir() / "sessions.json", budget=5)
        session = sessions.by_id(index, session_id.strip())
        if session is None:
            notify.send([f"No Claude Code session {session_id.strip()}"])
            _error(f"no session {session_id.strip()} in {sessions.projects_dir()}")
            return 1
        sessions.link(links_path, row["label"], session)
        notify.send([f"Linked {row['label']} to its feature session"])
        return 0
    session = feature_session(row)
    if session is None:
        _error(f"no feature session for {row['label']}")
        return 1
    command = f"cd {shlex.quote(session['cwd'])} && claude --resume {shlex.quote(session['id'])}"
    ok, message = terminal.open_command(command, terminal.pick_app(config.load()["terminal"]))
    if not ok:
        _error(message or "osascript failed")
        return 1
    return 0


def _first_clone(slug: str, cfg: dict) -> str:
    """Clone a repo chip has not seen on this Mac, telling the user (it can take a while) and what it lacks."""
    notify.send([f"Cloning {slug}… (first review of this repo)"])
    try:
        clone = clone_repo(slug)
    except repos.CloneError as exc:
        raise repos.CloneError(f"could not clone {slug} (do you have access? gh auth status): {exc}") from exc
    missing = [name for name in [project.LOCAL_SETTINGS] + list(cfg["worktree_links"])
               if not (Path(clone) / name).exists()]
    if missing:
        notify.send([f"{slug} was cloned into {clone} without {', '.join(missing)}: tools such as Laravel Boost "
                     f"will not run. Clone it into your code folder (or set it up there) to use them."])
    return clone


def _project_skill(clone: str) -> dict:
    """The repo's own review skill, or the built-in review when it has none."""
    name = project.find_review_skill(clone)
    if name is None:
        return config.DEFAULT_SKILL
    return {"name": project.skill_label(name), "prompt": project.prompt_template(name)}


def _known_run(run_id: str) -> bool:
    if runs.find_by_id(runs.load(_runs_path()), run_id) is None:
        _error(f"no chip run {run_id}")
        return False
    return True


def cmd_attach(args) -> int:
    """Open the review session: attach while it runs in the background, else resume it in its repo."""
    found = runs.find_by_id(runs.load(_runs_path()), args.id)
    if found is None:
        _error(f"no chip run {args.id}")
        return 2
    record = found[1]
    if args.id in runs.fetch_agents() or not record.get("session_id"):
        command = f"claude attach {args.id}"
    else:
        cwd = record.get("cwd") or str(Path.home())
        command = f"cd {shlex.quote(cwd)} && claude --resume {shlex.quote(record['session_id'])}"
    ok, message = terminal.open_command(command, terminal.pick_app(config.load()["terminal"]))
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
    record = records.pop(found[0])
    if record.get("worktree") and not any(r.get("worktree") == record["worktree"] for r in records.values()):
        project.remove(record["clone"], record["worktree"], record["label"].rsplit("#", 1)[-1])
    runs.save(_runs_path(), records)
    return 0


def cmd_act(args, runner) -> int:
    """Approve / request changes / comment on a PR to review; merge / close / ready / draft / comment on
    your own. Asks in a dialog first, then refetches so every part of the menu shows the new state."""
    row = _find_row(args.label)
    if row is None:
        _error(f"PR {args.label} is not in the list")
        return 2
    try:
        done, message = actions.run(args.action, row)
    except actions.ActionError as exc:
        notify.send([f"Could not {args.action} {args.label}: {exc}"])
        _error(str(exc))
        return 1
    if not done:  # cancelled in the dialog
        return 0
    store.load_all(runner, force=True)
    notify.send([message])
    print(message)
    return 0


def cmd_nudge(args) -> int:
    """Re-request review from the reviewers of one of the user's PRs who have not approved it."""
    row = _find_row(args.label)
    if row is None or row.get("kind") != "mine":
        _error(f"{args.label} is not one of your open PRs")
        return 2
    logins = [login for login, state in row["reviewers"].items() if state != "APPROVED"]
    if not logins:
        _error(f"nobody to re-request on {args.label}")
        return 2
    cmd = ["gh", "api", "-X", "POST", f"repos/{row['repo']}/pulls/{row['number']}/requested_reviewers"]
    for login in logins:
        cmd += ["-f", f"reviewers[]={login}"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        notify.send([f"Could not re-request review on {args.label}"])
        _error((proc.stderr or proc.stdout).strip())
        return 1
    notify.send([f"Re-requested review from {', '.join(logins)} on {args.label}"])
    return 0


SEARCH_DIALOG = (
    'display dialog "Search pull requests: title, number, project, author, reviewer or Jira key" '
    'default answer "{q}" with title "chip" buttons {{"Clear", "Cancel", "Search"}} '
    'default button "Search" cancel button "Cancel"'
)
DIALOG_RE = re.compile(r"button returned:(\w+), text returned:(.*)")


def cmd_search(args) -> int:
    """Ask for search text in a native dialog (menus have no text field) and save it for the menu."""
    if args.clear:
        store.save_query("")
        return 0
    current = store.load_query().replace("\\", "\\\\").replace('"', '\\"')
    proc = subprocess.run(["osascript", "-e", SEARCH_DIALOG.format(q=current)], capture_output=True, text=True)
    match = DIALOG_RE.search(proc.stdout or "")
    if proc.returncode != 0 or not match:  # Cancel
        return 0
    store.save_query("" if match.group(1) == "Clear" else match.group(2))
    return 0


def cmd_project(args) -> int:
    if args.action == "arrange":
        config.arrange_projects(args.order or [], args.hidden or [])
        return 0
    if args.action == "all":
        config.show_all_projects()
    elif args.name:
        config.toggle_project(args.name)
    else:
        _error("usage: chip project toggle <name> | chip project all")
        return 2
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
    print(swiftbar.build_menu(plugin, force=args.force, fetch_runner=runner, view=args.view or store.load_view(),
                              deliver=args.deliver, panes=args.panes))
    return 0


def cmd_update(args) -> int:
    if args.check:
        latest = updates.latest_release(cache_dir() / "update.json", now=time.time(), force=True)
        print(latest or "no release found")
        return 0
    app = installer.bundled()
    if app:
        latest = updates.latest_release(cache_dir() / "update.json", now=time.time(), force=True)
        if not latest or not updates.is_newer(latest, __version__):
            print(f"GitHubBar v{__version__} is up to date")
            return 0
        ok, message = updates.update_app(app, latest)
        notify.send([message if ok else f"GitHubBar update stopped: {message}"])
        return 0 if ok else 1
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
    p_repo.add_argument("--clone", action="store_true", help="clone into the clone folder (~/.cache/chip/repos) if missing")
    p_config = sub.add_parser("config", help="config file: init | check | path | open | example | set KEY VALUE")
    p_config.add_argument("action", choices=["init", "check", "path", "open", "example", "set"])
    p_config.add_argument("key", nargs="?")
    p_config.add_argument("value", nargs="?")
    p_prompt = sub.add_parser("prompt", help="review prompt for a PR label from the configured skill")
    p_prompt.add_argument("label")
    p_prompt.add_argument("--skill", type=int, default=1)
    p_run = sub.add_parser("run", help="start a background review for a PR label")
    p_run.add_argument("label")
    p_run.add_argument("--skill", type=int, default=1)
    p_run.add_argument("--address", action="store_true", help="run an address-review skill on your own PR")
    p_run.add_argument("--feature", action="store_true",
                       help="with --address: continue the Claude Code session where the PR's feature was built")
    p_run.add_argument("--project", action="store_true",
                       help="run the repo's own review skill on the PR in a worktree (built-in review if it has none)")
    p_search = sub.add_parser("search", help="search the menu (native dialog); --clear removes the search")
    p_search.add_argument("--clear", action="store_true")
    p_project = sub.add_parser("project", help="projects in the menu: toggle NAME | all | arrange --order … --hidden …")
    p_project.add_argument("action", choices=["toggle", "all", "arrange"])
    p_project.add_argument("name", nargs="?")
    p_project.add_argument("--order", nargs="*", help="arrange: projects in this order first")
    p_project.add_argument("--hidden", nargs="*", help="arrange: the projects to hide")
    sub.add_parser("nudge", help="re-request review from reviewers who have not approved").add_argument("label")
    p_session = sub.add_parser("session", help="open | link [id] | unlink the feature session of your PR")
    p_session.add_argument("action", choices=["open", "link", "unlink"])
    p_session.add_argument("label")
    p_session.add_argument("id", nargs="?")
    p_act = sub.add_parser("act", help="approve | request-changes | comment a PR; merge | close | ready | draft yours")
    p_act.add_argument("label")
    p_act.add_argument("action", choices=sorted(actions.ACTIONS))
    for name in ("attach", "stop", "forget"):
        sub.add_parser(name, help=f"{name} a chip review by session id").add_argument("id")
    sub.add_parser("copy", help="copy a PR link").add_argument("label")
    p_swiftbar = sub.add_parser("swiftbar", help="print the SwiftBar menu (used by the menu bar plugin)")
    p_swiftbar.add_argument("--force", action="store_true", help="refetch from GitHub now")
    p_swiftbar.add_argument("--view", choices=list(store.VIEWS),
                            help="override the remembered tab: review (default) or mine")
    p_swiftbar.add_argument("--deliver", action="store_true",
                            help="print queued notifications in the title block (GitHubBar posts them)")
    p_swiftbar.add_argument("--panes", action="store_true",
                            help="print both tabs, each after a pane= marker (GitHubBar switches tabs in place)")
    sub.add_parser("notifications", help="clear the Recent notifications menu").add_argument(
        "--clear", action="store_true", required=True)
    sub.add_parser("view", help="switch the menu tab: review | mine").add_argument("tab", choices=list(store.VIEWS))
    sub.add_parser("install", help="link chip, install the /chip skill, MCP server and menu bar plugin")
    sub.add_parser("uninstall", help="remove what `chip install` added")
    p_update = sub.add_parser("update", help="install the latest release (a clone pulls and rebuilds)")
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
    if args.cmd == "view":
        store.save_view(args.tab)
        return 0
    if args.cmd == "notifications":
        (cache_dir() / "history.json").unlink(missing_ok=True)
        return 0
    if args.cmd == "search":
        return cmd_search(args)
    if args.cmd == "project":
        return cmd_project(args)
    if args.cmd == "nudge":
        return cmd_nudge(args)
    if args.cmd == "session":
        return cmd_session(args)
    if args.cmd == "act":
        return cmd_act(args, runner or fetch.run_gh_graphql)
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
