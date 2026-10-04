"""`chip swiftbar`: the menu bar menu rendered as SwiftBar plugin output (English UI)."""
from __future__ import annotations

import base64
import json
import re
import textwrap
import time
from datetime import datetime
from pathlib import Path
import os
from typing import Dict, List, Optional

from chip import __version__, config, fetch, model, notify, project, runs, store, updates, watch

GREY = "#8E8E93"
PAGE = 12
PER_PROJECT = 5  # rows per project on the top level; the rest go into a "N more" submenu
HEADER = {"size": "11", "color": GREY}
ROW_FONT = {"font": "Menlo", "size": "12"}
ICON_FILE = Path(__file__).resolve().parent / "assets" / "github-mark.png"
SIZE_RE = re.compile(r"\+(\d+)/-(\d+) (\d+)f")
STATUS = {
    model.REREVIEW: ("Re-review", "arrow.triangle.2.circlepath", "#FF9500"),
    model.NEW: ("New", "sparkle", "#34C759"),
    model.WAITING: ("Waiting on author", "hourglass", GREY),
    model.COMMENTED: ("Commented", "text.bubble", GREY),
    model.APPROVED: ("Approved", "checkmark.seal", GREY),
}
# Status styles (config `status_style`): dots (default), emoji, symbols (SF Symbols).
SHORT = {model.REREVIEW: "Re-review", model.NEW: "New", model.WAITING: "Waiting",
         model.COMMENTED: "Commented", model.APPROVED: "Approved"}
DOT = {model.REREVIEW: "🟠", model.NEW: "🟢", model.WAITING: "⚪", model.COMMENTED: "⚪", model.APPROVED: "⚪"}
EMOJI = {model.REREVIEW: "🔁", model.NEW: "🆕", model.WAITING: "⏳", model.COMMENTED: "💬", model.APPROVED: "✅"}
LEGEND = "🔁 Re-review · 🆕 New · 💬 Commented · ⏳ Waiting on author"
RUN_DOT = {"running": "🔵", "needs_you": "🟡", "done": "🟢", "gone": "⚪", "other": "⚪"}
# A PR row with a live or finished chip review shows that instead of its review status.
RUN_SHORT = {"running": "Reviewing", "needs_you": "Needs you", "done": "Reviewed"}
RUN_ROW_DOT = {"running": "🔵", "needs_you": "🟡", "done": "✅"}
STYLES = (("dots", "Colored dots + label"), ("emoji", "Emoji"), ("symbols", "Symbols"))
# The user's own PRs (always emoji dots).
MINE_DOT = {model.CHANGES: "🔴", model.CI_FAILED: "❌", model.CONFLICT: "⚠️", model.THREADS: "💬",
            model.READY: "✅", model.AWAITING: "⚪", model.DRAFT: "⚪"}
MINE_SHORT = {model.CHANGES: "Changes", model.CI_FAILED: "CI failed", model.CONFLICT: "Conflict",
              model.THREADS: "{n} threads", model.READY: "Approved", model.AWAITING: "Waiting", model.DRAFT: "Draft"}
MINE_LONG = {model.CHANGES: "Changes requested", model.CI_FAILED: "CI failed", model.CONFLICT: "Merge conflict",
             model.THREADS: "Unresolved review threads", model.READY: "Approved — ready to merge",
             model.AWAITING: "Waiting for review", model.DRAFT: "Draft"}
MINE_ACTIONABLE = (model.CHANGES, model.CI_FAILED, model.CONFLICT, model.THREADS)
MINE_RUN_SHORT = {"running": "Drafting", "needs_you": "Needs you", "done": "Drafted"}
REVIEW_MARK = {"APPROVED": "✓", "CHANGES_REQUESTED": "✗", "COMMENTED": "💬", "DISMISSED": "–"}
RUN_SYMBOL = {
    "running": ("circle.lefthalf.filled", "#0A84FF"),
    "needs_you": ("exclamationmark.triangle.fill", "#FFCC00"),
    "done": ("checkmark.circle.fill", "#34C759"),
    "gone": ("xmark.circle", GREY),
    "other": ("questionmark.circle", GREY),
}


def sf_config(color: str) -> str:
    """SwiftBar `sfconfig`: base64 JSON that tints an SF Symbol (palette mode works on SwiftBar 2.1)."""
    return base64.b64encode(json.dumps({"renderingMode": "Palette", "colors": [color]}).encode()).decode()


def symbol(name: str, color: str) -> dict:
    return {"sfimage": name, "sfconfig": sf_config(color)}


def icon_b64() -> str:
    return base64.b64encode(ICON_FILE.read_bytes()).decode()


def esc(text) -> str:
    text = str(text).replace("|", "¦")
    return "​" + text if text.startswith("-") else text


def _param(key: str, value) -> str:
    value = str(value)
    return f'{key}="{value}"' if " " in value else f"{key}={value}"


def item(text, depth: int = 0, **params) -> str:
    line = "--" * depth + esc(text)
    if params:
        line += " | " + " ".join(_param(k, v) for k, v in params.items())
    return line


def separator(depth: int) -> str:
    return "--" * depth + "---"


def action(plugin: str, *args, refresh: bool = True) -> dict:
    params = {"bash": plugin, "terminal": "false"}
    for i, arg in enumerate(args, 1):
        params[f"param{i}"] = arg
    if refresh:
        params["refresh"] = "true"
    return params


def plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def ago(wait: str) -> str:
    unit = {"m": "minute", "h": "hour", "d": "day"}[wait[-1]]
    return f"{plural(int(wait[:-1]), unit)} ago"


def details(r: dict) -> str:
    parts = []
    match = SIZE_RE.match(r["size"])
    if match:
        parts.append(f"+{match.group(1)} −{match.group(2)} · {plural(int(match.group(3)), 'file')}")
    parts.append("base " + r["base"] + (" (stacked)" if r["stacked"] else ""))
    if r["jira"]:
        parts.append(r["jira"])
    if r["conflict"]:
        parts.append("conflict")
    return " · ".join(parts)


def _project(r: dict) -> str:
    return r["label"].split("#")[0]


def _cut(text: str, width: int) -> str:
    return text if len(text) <= width else text[: width - 1] + "…"


def _active_run(r: dict, ctx: dict) -> Optional[tuple]:
    """The latest (record, view) of a chip review on this PR that is running, waiting or done."""
    runs = [rv for rv in ctx["runs_by_label"].get(r["label"], {}).values()
            if rv[1]["kind"] in RUN_SHORT and not rv[0].get("resolved_at")]
    return max(runs, key=lambda rv: rv[0].get("started_at", 0)) if runs else None


def _row(r: dict, depth: int, style: str, run: Optional[tuple] = None) -> str:
    """The top-level PR line in the chosen status style; the tooltip names the status (or the review)."""
    name, sf_name, color = STATUS[r["status"]]
    dot, short, mark, tooltip = DOT[r["status"]], SHORT[r["status"]], EMOJI[r["status"]], name
    if run:
        record, view = run
        dot = mark = RUN_ROW_DOT[view["kind"]]
        short = RUN_SHORT[view["kind"]]
        sf_name, color = RUN_SYMBOL[view["kind"]]
        tooltip = f"{record['skill']} · {view['text']}"
    number = f"#{r['number']}"
    if style == "dots":
        text = f"{dot} {number:<7}{short:<11}{_cut(r['title'], 38):<39} {r['author']}"
        return item(text, depth, tooltip=tooltip, **ROW_FONT)
    if style == "emoji":
        text = f"{mark} {number:<7}{_cut(r['title'], 44):<45} {r['author']}"
        return item(text, depth, tooltip=tooltip, **ROW_FONT)
    text = f"{number:<7}{_cut(r['title'], 44):<45} {r['author']}"
    return item(text, depth, **symbol(sf_name, color), tooltip=tooltip, **ROW_FONT)


def _round_lines(record: dict, view: dict, d: int, label: str, ctx: dict, run_args: tuple) -> List[str]:
    """`Last review · …` for one skill on one PR, then View / Continue / Open last session."""
    number = record.get("round", 1)
    head = f"Last review · {record['skill']} · round {number}"
    if view["kind"] in ("running", "needs_you") and not record.get("resolved_at"):
        lines = [item(f"{head} · {view['text']}", d, disabled="true")]
        text = "View running review" if view["kind"] == "running" else "Open session (needs you)"
        lines.append(item(text, d, sfimage="eye", **action(ctx["plugin"], "attach", record["id"], refresh=False)))
        return lines
    when = datetime.fromtimestamp(record.get("done_at", record["started_at"])).strftime("%H:%M")
    state = f"resolved ({record['resolved_by']})" if record.get("resolved_at") else view["kind"]
    return [
        item(f"{head} · {when} · {state}", d, disabled="true"),
        item(f"Continue review (round {number + 1})", d, sfimage="play.fill", keep="run",
             **action(ctx["plugin"], "run", label, *run_args)),
        item("Open last session", d, sfimage="eye", **action(ctx["plugin"], "attach", record["id"], refresh=False)),
    ]


def _reviewers_text(r: dict) -> str:
    if r["reviewers"]:
        return " ".join(f"{login} {REVIEW_MARK.get(state, '?')}" for login, state in r["reviewers"].items())
    if r["requested"]:
        return "→ " + ", ".join(r["requested"])
    return "—"


def _mine_row(r: dict, depth: int, run: Optional[tuple]) -> str:
    status = r["mine_status"]
    dot, short, tooltip = MINE_DOT[status], MINE_SHORT[status].format(n=r["unresolved"]), MINE_LONG[status]
    if run:
        record, view = run
        dot, short = RUN_ROW_DOT[view["kind"]], MINE_RUN_SHORT[view["kind"]]
        tooltip = f"{record['skill']} · {view['text']}"
    number = f"#{r['number']}"
    text = f"{dot} {number:<7}{short:<11}{_cut(r['title'], 34):<35} {_cut(_reviewers_text(r), 26)}"
    return item(text, depth, tooltip=tooltip, **ROW_FONT)


def mine_lines(r: dict, depth: int, ctx: dict) -> List[str]:
    """One of the user's own PRs: status, reviewers, Address-review rounds, Re-request review, links."""
    lines = [_mine_row(r, depth, _active_run(r, ctx))]
    d = depth + 1
    lines.append(item(r["label"], d, disabled="true"))
    for chunk in textwrap.wrap(r["title"], 60) or [""]:
        lines.append(item(chunk, d, disabled="true"))
    lines.append(item(f"{MINE_LONG[r['mine_status']]} · opened {ago(r['wait'])}", d, disabled="true"))
    reviews = " · ".join(f"{login} {REVIEW_MARK.get(state, '?')}" for login, state in r["reviewers"].items())
    if r["requested"]:
        reviews = " · ".join(filter(None, [reviews, "requested: " + ", ".join(r["requested"])]))
    lines.append(item(f"Reviews: {reviews or 'none yet'}", d, disabled="true"))
    if r["unresolved"]:
        lines.append(item(plural(r["unresolved"], "unresolved thread"), d, disabled="true"))
    lines.append(item(details(r), d, disabled="true"))
    lines.append(separator(d))
    my_runs = ctx["runs_by_label"].get(r["label"], {})
    for i, skill in enumerate(ctx["address_skills"], 1):
        if not config.applies(skill, r):
            continue
        run = my_runs.get(skill["name"])
        if run is None:
            lines.append(item(f'Run "{skill["name"]}"', d, sfimage="play.fill", keep="run",
                              **action(ctx["plugin"], "run", r["label"], "--skill", i, "--address")))
        else:
            lines.extend(_round_lines(run[0], run[1], d, r["label"], ctx, ("--skill", i, "--address")))
    pending = [login for login, state in r["reviewers"].items() if state != "APPROVED"]
    if pending:
        lines.append(item(f"Re-request review ({', '.join(pending)})", d, sfimage="bell",
                          **action(ctx["plugin"], "nudge", r["label"])))
    lines.append(separator(d))
    lines.append(item("Open on GitHub", d, href=r["url"], sfimage="arrow.up.right.square"))
    lines.append(item("Copy link", d, sfimage="doc.on.doc", **action(ctx["plugin"], "copy", r["label"], refresh=False)))
    return lines


def review_buttons(r: dict, ctx: dict) -> List[tuple]:
    """(name, run args) per review button: the configured skills that apply to this PR (their `repos` /
    `languages`), plus the repo's own review skill. With neither, one built-in "Review" button."""
    buttons = [(skill["name"], ("--skill", i)) for i, skill in enumerate(ctx["skills"], 1)
               if config.applies(skill, r)]
    own = ctx.get("project_skills", {}).get(r["repo"])
    if own:
        buttons.append((project.skill_label(own), ("--project",)))
    elif not buttons:
        buttons.append((config.DEFAULT_SKILL["name"], ("--project",)))
    return buttons


def pr_lines(r: dict, depth: int, ctx: dict) -> List[str]:
    if r.get("kind") == "mine":
        return mine_lines(r, depth, ctx)
    lines = [_row(r, depth, ctx["style"], _active_run(r, ctx))]
    name = STATUS[r["status"]][0]
    d = depth + 1
    lines.append(item(r["label"], d, disabled="true"))
    for chunk in textwrap.wrap(r["title"], 60) or [""]:
        lines.append(item(chunk, d, disabled="true"))
    lines.append(item(f"{name} · by {r['author']} · opened {ago(r['wait'])}", d, disabled="true"))
    lines.append(item(details(r), d, disabled="true"))
    lines.append(separator(d))
    my_runs = ctx["runs_by_label"].get(r["label"], {})
    for name, run_args in review_buttons(r, ctx):
        run = my_runs.get(name)
        if run is None and run_args == ("--project",):
            run = next((v for v in my_runs.values() if v[0].get("auto")), None)
        if run is None:
            lines.append(item(f'Run "{name}"', d, sfimage="play.fill", keep="run",
                              **action(ctx["plugin"], "run", r["label"], *run_args)))
            continue
        record, view = run
        lines.extend(_round_lines(record, view, d, r["label"], ctx, run_args))
    lines.append(separator(d))
    lines.append(item("Open on GitHub", d, href=r["url"], sfimage="arrow.up.right.square"))
    lines.append(item("Copy link", d, sfimage="doc.on.doc", **action(ctx["plugin"], "copy", r["label"], refresh=False)))
    return lines


def _project_order(rows: List[dict]) -> List[str]:
    counts: Dict[str, int] = {}
    actionable: Dict[str, int] = {}
    for r in rows:
        p = _project(r)
        counts[p] = counts.get(p, 0) + 1
        mine_actionable = r.get("kind") == "mine" and r.get("mine_status") in MINE_ACTIONABLE
        actionable[p] = actionable.get(p, 0) + (r["status"] in (model.REREVIEW, model.NEW) or mine_actionable)
    return sorted(counts, key=lambda p: (-actionable[p], -counts[p], p))


def pr_pages(rows: List[dict], depth: int, ctx: dict) -> List[str]:
    """Rows grouped by project, 12 per page; each further page sits in a nested `Next ›` submenu."""
    order = _project_order(rows)
    entries = [(p, r) for p in order for r in rows if _project(r) == p]
    counts = {p: sum(1 for q, _ in entries if q == p) for p in order}
    lines: List[str] = []
    start = 0
    while start < len(entries):
        page = entries[start:start + PAGE]
        prev = None
        for i, (proj, r) in enumerate(page):
            if proj != prev:
                continued = i == 0 and start > 0 and entries[start - 1][0] == proj
                head = f"{proj.upper()} (cont.)" if continued else f"{proj.upper()} · {plural(counts[proj], 'PR')}"
                lines.append(item(head, depth, **HEADER))
                prev = proj
            lines.extend(pr_lines(r, depth, ctx))
        start += PAGE
        if start < len(entries):
            end = min(start + PAGE, len(entries))
            lines.append(item(f"Next {end - start} ›  ({start + 1}–{end} of {len(entries)})", depth))
            depth += 1
    return lines


def _paged_rows(rows: List[dict], depth: int, ctx: dict) -> List[str]:
    """Plain PR rows, 12 per page; each further page sits in a nested `Next ›` submenu."""
    lines: List[str] = []
    start = 0
    while start < len(rows):
        for r in rows[start:start + PAGE]:
            lines.extend(pr_lines(r, depth, ctx))
        start += PAGE
        if start < len(rows):
            end = min(start + PAGE, len(rows))
            lines.append(item(f"Next {end - start} ›  ({start + 1}–{end} of {len(rows)})", depth))
            depth += 1
    return lines


def _tag(lines: List[str], depth: int, params: dict) -> List[str]:
    """Add params to the items at exactly `depth` (not to their submenus or separators)."""
    prefix, extra = "--" * depth, " ".join(_param(k, v) for k, v in params.items())
    tagged = []
    for line in lines:
        if line.startswith(prefix) and not line[len(prefix):].startswith("-"):
            line += (" " if " | " in line else " | ") + extra
        tagged.append(line)
    return tagged


def project_sections(rows: List[dict], depth: int, ctx: dict, hidden_projects: frozenset = frozenset()) -> List[str]:
    """Every project gets a header and its first PER_PROJECT rows; the rest go into `N more in X ›`.

    Each project's lines carry `proj=<name>` (plus `hidden=true` for hidden projects, which are still
    listed) so GitHubBar can show or hide a project in place from the Projects submenu."""
    lines: List[str] = []
    for proj in _project_order(rows):
        prs = [r for r in rows if _project(r) == proj]
        section = [item(f"{proj.upper()} · {plural(len(prs), 'PR')}", depth, **HEADER)]
        for r in prs[:PER_PROJECT]:
            section.extend(pr_lines(r, depth, ctx))
        rest = prs[PER_PROJECT:]
        if rest:
            section.append(item(f"{len(rest)} more in {proj.upper()} ›", depth, color=GREY))
            section.extend(_paged_rows(rest, depth + 1, ctx))
        lines.extend(_tag(section, depth, {"proj": proj, **({"hidden": "true"} if proj in hidden_projects else {})}))
    return lines


def run_lines(records: Dict[str, dict], views: Dict[str, dict], ctx: dict) -> List[str]:
    records = {key: rec for key, rec in records.items() if not rec.get("resolved_at")}
    if not records:
        return []
    lines = ["---", item("Reviews by GitHubBar", 0, **HEADER)]
    for key, rec in sorted(records.items(), key=lambda kv: -kv[1].get("started_at", 0)):
        view = views[key]
        text = f"{rec['label']} · {rec['skill']} · {view['text']}"
        if ctx["style"] == "symbols":
            sf_name, color = RUN_SYMBOL[view["kind"]]
            lines.append(item(text, 0, **symbol(sf_name, color)))
        else:
            lines.append(item(f"{RUN_DOT[view['kind']]} {text}", 0))
        if view["kind"] != "gone":
            lines.append(item("View session", 1, sfimage="eye", **action(ctx["plugin"], "attach", rec["id"], refresh=False)))
        if view["kind"] in ("running", "needs_you"):
            lines.append(item("Stop", 1, sfimage="stop.circle", **action(ctx["plugin"], "stop", rec["id"])))
        lines.append(item("Remove", 1, sfimage="trash", **action(ctx["plugin"], "forget", rec["id"])))
        lines.append(item("Open on GitHub", 1, href=rec["url"], sfimage="arrow.up.right.square"))
    return lines


def _matches(n: int) -> str:
    return f"{n} match{'' if n == 1 else 'es'}"


def _haystack(r: dict) -> str:
    """What search matches: label, repo, title, author, Jira key and reviewers (lowercase)."""
    return " ".join([r["label"], r["repo"], r["title"], r["author"], r.get("jira", ""),
                     " ".join(r.get("reviewers", {})), " ".join(r.get("requested", []))]).lower()


def search_lines(rows: List[dict], ctx: dict) -> List[str]:
    """For GitHubBar's in-menu search field: every PR of the tab as a top-level row tagged with what it
    matches (`find=`), hidden until the user types, plus a "no matches" line."""
    lines = []
    for r in rows:
        find = " ".join(re.sub(r"[\"|¦]", " ", _haystack(r)).split())
        lines.extend(_tag(pr_lines(r, 0, ctx), 0, {"searchonly": "true", "find": find}))
    lines.append(item("No matching pull requests", 0, color=GREY, nomatch="true"))
    return lines


def _filter(rows: List[dict], hidden_projects: set, query: str = "") -> List[dict]:
    """Drop hidden projects and rows that miss any search word (label, repo, title, author, Jira, reviewers)."""
    words = query.lower().split()
    kept = []
    for r in rows:
        if _project(r) in hidden_projects:
            continue
        haystack = _haystack(r)
        if all(word in haystack for word in words):
            kept.append(r)
    return kept


def _controls(plugin: str, rows: List[dict], hidden_projects: set, query: str, matches: int,
              live_search: bool = False, project_skills: Optional[Dict[str, str]] = None) -> List[str]:
    """Search (GitHubBar: a field in the menu; otherwise a native dialog) and the Projects submenu
    with a checkmark on every shown project."""
    lines = []
    if live_search:
        lines.append(item("Search pull requests", 0, searchfield="true"))
    elif query:
        lines.append(item(f'"{query}" · {_matches(matches)} — Clear search', 0, sfimage="xmark.circle",
                          **action(plugin, "search", "--clear")))
    if not live_search:
        lines.append(item("Search…", 0, sfimage="magnifyingglass", **action(plugin, "search")))
    projects = sorted({_project(r) for r in rows})
    if projects:
        lines.append(item("Projects", 0, sfimage="square.grid.2x2"))
        lines.append(item("Show all", 1, keep="all", **action(plugin, "project", "all")))
        for proj in projects:
            checked = {} if proj in hidden_projects else {"checked": "true"}
            lines.append(item(proj, 1, keep="toggle", **checked, **action(plugin, "project", "toggle", proj)))
    return lines


def event_params(plugin: str, event: dict) -> dict:
    """What clicking a notification does: open the review session, or open the PR/release page."""
    if event.get("run"):
        return action(plugin, "attach", event["run"], refresh=False)
    return {"href": event["href"]} if event.get("href") else {}


def _when(at: float, now: float) -> str:
    stamp = datetime.fromtimestamp(at)
    return stamp.strftime("%H:%M" if stamp.date() == datetime.fromtimestamp(now).date() else "%b %d")


def recent_lines(plugin: str, history: List[dict], now: float) -> List[str]:
    if not history:
        return []
    lines = [item("Recent notifications", 0, sfimage="bell")]
    for event in history:
        lines.append(item(f"{_when(event.get('at', now), now)}  {event['text']}", 1, **event_params(plugin, event)))
    lines += [separator(1), item("Clear", 1, sfimage="trash", **action(plugin, "notifications", "--clear"))]
    return lines


def _settings(plugin: str, style: str, version: str) -> List[str]:
    lines = [item("Settings", 0, sfimage="gearshape"), item("Status style", 1, sfimage="paintpalette")]
    for value, label in STYLES:
        checked = {"checked": "true"} if value == style else {}
        lines.append(item(label, 2, keep="radio", **checked, **action(plugin, "config", "set", "status_style", value)))
    lines += [
        item("Open config", 1, sfimage="doc.text", **action(plugin, "config", "open", refresh=False)),
        item("Reinstall", 1, sfimage="arrow.triangle.2.circlepath", **action(plugin, "install")),
        item("Check for updates", 1, sfimage="arrow.down.circle", **action(plugin, "update", "--check")),
        item("Open GitHubBar on GitHub", 1, href=f"https://github.com/{updates.REPO}", sfimage="link"),
        item(f"About GitHubBar v{version}", 1, disabled="true"),
    ]
    return lines


def render(inbox_all: Optional[dict], records: Dict[str, dict], views: Dict[str, dict], cfg: dict,
           plugin: str, version: str, newer: Optional[str] = None, error: Optional[str] = None,
           now: Optional[float] = None, view: str = "review", query: str = "",
           history: Optional[List[dict]] = None, deliver: Optional[List[dict]] = None,
           live_search: bool = False, project_skills: Optional[Dict[str, str]] = None) -> List[str]:
    """One menu: `review` (PRs waiting for the user's review) or `mine` (the user's own PRs).

    `deliver` events become extra title-block lines (`notify=true`) that GitHubBar posts natively."""
    now = time.time() if now is None else now
    hidden_projects = set(cfg.get("hidden_projects", []))
    style = cfg.get("status_style", "dots")
    mine_view = view == "mine"
    review_shown = _filter((inbox_all or {}).get("rows", []), hidden_projects)  # counts ignore the search
    mine_shown = _filter((inbox_all or {}).get("mine", []), hidden_projects)
    review_open = [r for r in review_shown if not r["draft"] and r["status"] != model.APPROVED]
    # "To do" counts: PRs waiting on the user (model.needs_review / model.MINE_ACTION); tabs show "to do / all".
    count = sum(1 for r in review_open if model.needs_review(r))
    mine_todo = sum(1 for r in mine_shown if r["mine_status"] in model.MINE_ACTION)
    active = [v["kind"] for v in views.values()]
    todo = ([str(count)] if count else []) + ([f"⚠{mine_todo}"] if mine_todo else [])
    running = [f"{dot}{active.count(kind)}" for kind, dot in (("running", "🔵"), ("needs_you", "🟡")) if kind in active]
    tip = (f"{plural(count, 'PR')} to review · {mine_todo} of your PRs need you"
           if not error else f"Could not refresh: {error[:120]}")
    title = " ".join(filter(None, [" · ".join(todo)] + running))  # e.g. "19 · ⚠8 🔵1"
    lines = [item("!" if error else title, 0, templateImage=icon_b64(), tooltip=tip)]
    lines += [item(event["text"], 0, notify="true", **event_params(plugin, event)) for event in deliver or []]
    lines.append("---")

    all_rows = (inbox_all or {}).get("mine" if mine_view else "rows", [])
    records = {k: rec for k, rec in records.items() if (rec.get("kind") == "address") == mine_view}
    views = {k: views[k] for k in records}
    runs_by_label: Dict[str, dict] = {}
    for key, rec in records.items():
        runs_by_label.setdefault(rec["label"], {})[rec["skill"]] = (rec, views[key])
    ctx = {"plugin": plugin, "skills": cfg["skills"], "address_skills": cfg.get("address_skills", []),
           "project_skills": project_skills or {},
           "runs_by_label": runs_by_label, "style": style}
    rows = _filter(all_rows, hidden_projects, query)
    listed = _filter(all_rows, set(), query)  # hidden projects too, tagged hidden, for in-place toggling
    if newer:
        lines.append(item(f"Update available: v{newer} — Update now", 0, **symbol("arrow.up.circle.fill", "#FF9500"),
                          color="#FF9500", **action(plugin, "update")))
    if error:
        lines.append(item(f"Could not refresh: {error[:90]}", 0, sfimage="exclamationmark.triangle", color="#FF3B30"))
    for message in cfg.get("errors", [])[:1]:
        lines.append(item(f"Config: {message[:90]} (using defaults)", 0, sfimage="gearshape", color="#FF9500"))

    if mine_view:
        visible, hidden = rows, []
    else:
        visible = [r for r in rows if not r["draft"] and r["status"] != model.APPROVED]
        hidden = [r for r in rows if r["draft"] or r["status"] == model.APPROVED]
    if inbox_all is not None:
        # Tabs: GitHubBar shows `tab=` items as one segmented control that switches without closing the menu.
        for name, text in (("review", f"Review requests · {count} / {len(review_open)}"),
                           ("mine", f"My pull requests · {mine_todo} / {len(mine_shown)}")):
            checked = {"checked": "true"} if name == view else {}
            lines.append(item(text, 0, tab=name, **checked, **action(plugin, "view", name)))
        updated = datetime.fromtimestamp(inbox_all.get("fetched_at", now)).strftime("%H:%M")
        lines.append(item(f"Updated {updated}", 0, color=GREY, size="12"))
    lines.append(item("Refresh now", 0, sfimage="arrow.clockwise", keep="refresh",
                      **action(plugin, "swiftbar", "--force")))
    if inbox_all is not None:
        lines.append("---")
        lines.extend(_controls(plugin, all_rows, hidden_projects, query, len(rows), live_search))
        lines.append("---")
        body_start = len(lines)
        if mine_view:
            if not visible:
                lines.append(item("No open pull requests" + (" match" if query else ""), 0, color=GREY))
            lines.extend(project_sections(listed, 0, ctx, frozenset(hidden_projects)))
        else:
            fresh = [r for r in listed if not r["draft"] and r["status"] != model.APPROVED
                     and (r["status"] == model.REREVIEW or not r.get("stale"))]
            older = [r for r in visible if r["status"] != model.REREVIEW and r.get("stale")]
            if not visible:
                lines.append(item("Nothing waiting for your review", 0, color=GREY))
            elif style == "emoji":
                lines.append(item(LEGEND, 0, **HEADER))
            lines.extend(project_sections(fresh, 0, ctx, frozenset(hidden_projects)))
            if older:
                lines.append(item(f"Older than 30 days · {plural(len(older), 'PR')}", 0, sfimage="clock", color=GREY))
                lines.extend(pr_pages(older, 1, ctx))
        if live_search:
            # While searching, GitHubBar hides the `body=` lines and shows the matching search rows.
            lines[body_start:] = _tag(lines[body_start:], 0, {"body": "true"})
            lines.extend(search_lines(_filter(all_rows, hidden_projects), ctx))
    lines.extend(run_lines(records, views, ctx))
    lines.append("---")
    if hidden:
        lines.append(item(f"Show approved & drafts ({len(hidden)})", 0, sfimage="eye.slash"))
        lines.extend(pr_pages(hidden, 1, ctx))
    lines.extend(recent_lines(plugin, history or [], now))
    lines.extend(_settings(plugin, style, version))
    return lines


def build_menu(plugin: str, force: bool = False, fetch_runner=None, runner=None,
               now: Optional[float] = None, view: str = "review", deliver: bool = False,
               env: Optional[Dict[str, str]] = None, panes: bool = False) -> str:
    """One refresh: inbox (3-min cache), run states, release check, notifications, menu text.

    Under GitHubBar (GITHUBBAR_NOTIFY=1) notifications are queued; `deliver` drains them into the menu."""
    env = os.environ if env is None else env
    now = time.time() if now is None else now
    cfg = config.load()
    # A new PR notification fetches now; otherwise the inbox cache is reused (longer while notifications work).
    changed = None if force else watch.check(store.cache_dir() / "notifications.json", runner, now)
    ttl = store.WATCHED_TTL_SECONDS if changed is not None else store.CACHE_TTL_SECONDS
    inbox_all, error = store.load_all(fetch_runner or fetch.run_gh_graphql, force or bool(changed), ttl=ttl)
    runs_path = store.cache_dir() / "runs.json"
    records = runs.load(runs_path)
    agents = runs.fetch_agents(runner) if records else {}
    every_row = (inbox_all or {}).get("rows", []) + (inbox_all or {}).get("mine", [])
    rows_by_label = {r["label"]: r for r in every_row}  # mine too, or address rounds would look "closed"
    observed = runs.observe(records, agents, now)
    resolved = runs.resolve(records, rows_by_label, now, fetched=inbox_all is not None and not error)
    if runs.clean_worktrees(records) or resolved or observed:
        runs.save(runs_path, records)
    views = {key: runs.view(rec, agents.get(rec["id"]), now) for key, rec in records.items()}
    latest = updates.latest_release(store.cache_dir() / "update.json", runner, now)
    newer = latest if latest and updates.is_newer(latest, __version__) else None
    history_path, outbox_path = store.cache_dir() / "history.json", store.cache_dir() / "outbox.json"
    if inbox_all is not None:
        visible = model.visible_view(inbox_all)["rows"]
        notify_path = store.cache_dir() / "notify.json"
        current = notify.snapshot(visible, views, newer, inbox_all.get("mine", []))
        found = notify.events(notify.load(notify_path), current, visible, records)
        if found:
            notify.remember(history_path, found, now)
            if env.get("GITHUBBAR_NOTIFY"):
                notify.queue(outbox_path, found)
            else:
                notify.send([event["text"] for event in found], runner)
        notify.save(notify_path, current)
    pending = notify.cap(notify.drain(outbox_path)) if deliver else []
    args = (inbox_all, records, views, cfg, plugin, __version__, newer, error, now)
    extra = {"query": store.load_query(), "history": notify.load_list(history_path),
             "project_skills": project.known_skills({r["repo"] for r in every_row}, store.cache_dir() / "repos.json")}
    if not panes:
        return "\n".join(render(*args, view=view, deliver=pending, **extra))
    extra.update(query="", live_search=True)  # GitHubBar searches inside the menu
    return "\n".join(both_panes(render(*args, view="review", deliver=pending, **extra),
                                render(*args, view="mine", **extra), view))


def both_panes(review: List[str], mine: List[str], view: str) -> List[str]:
    """Both tabs in one menu for GitHubBar: review's title block, then each tab's body after a
    `pane=` marker line. The app shows the active pane and switches by hiding items, without closing the menu."""
    split = review.index("---")
    lines = review[:split + 1]
    for name, body in (("review", review[split + 1:]), ("mine", mine[mine.index("---") + 1:])):
        lines.append(item("", 0, pane=name, **({"active": "true"} if name == view else {})))
        lines.extend(body)
    return lines
