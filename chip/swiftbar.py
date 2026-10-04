"""`chip swiftbar`: the menu bar menu rendered as SwiftBar plugin output (English UI)."""
from __future__ import annotations

import base64
import json
import re
import textwrap
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from chip import __version__, config, fetch, model, notify, runs, store, updates

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
STYLES = (("dots", "Colored dots + label"), ("emoji", "Emoji"), ("symbols", "Symbols"))
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


def _row(r: dict, depth: int, style: str) -> str:
    """The top-level PR line in the chosen status style; the tooltip always names the status."""
    name, sf_name, color = STATUS[r["status"]]
    number = f"#{r['number']}"
    if style == "dots":
        text = f"{DOT[r['status']]} {number:<7}{SHORT[r['status']]:<11}{_cut(r['title'], 38):<39} {r['author']}"
        return item(text, depth, tooltip=name, **ROW_FONT)
    if style == "emoji":
        text = f"{EMOJI[r['status']]} {number:<7}{_cut(r['title'], 44):<45} {r['author']}"
        return item(text, depth, tooltip=name, **ROW_FONT)
    text = f"{number:<7}{_cut(r['title'], 44):<45} {r['author']}"
    return item(text, depth, **symbol(sf_name, color), tooltip=name, **ROW_FONT)


def pr_lines(r: dict, depth: int, ctx: dict) -> List[str]:
    lines = [_row(r, depth, ctx["style"])]
    name = STATUS[r["status"]][0]
    d = depth + 1
    lines.append(item(r["label"], d, disabled="true"))
    for chunk in textwrap.wrap(r["title"], 60) or [""]:
        lines.append(item(chunk, d, disabled="true"))
    lines.append(item(f"{name} · by {r['author']} · opened {ago(r['wait'])}", d, disabled="true"))
    lines.append(item(details(r), d, disabled="true"))
    lines.append(separator(d))
    my_runs = ctx["runs_by_label"].get(r["label"], {})
    for i, skill in enumerate(ctx["skills"], 1):
        again = " again" if skill["name"] in my_runs else ""
        lines.append(item(f'Run "{skill["name"]}"{again}', d, sfimage="play.fill",
                          **action(ctx["plugin"], "run", r["label"], "--skill", i)))
    for skill_name, (record, view) in my_runs.items():
        if view["kind"] == "gone":
            continue
        text = f"View running review ({skill_name})" if view["kind"] == "running" \
            else f"View review ({skill_name}) · {view['text']}"
        lines.append(item(text, d, sfimage="eye", **action(ctx["plugin"], "attach", record["id"], refresh=False)))
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
        actionable[p] = actionable.get(p, 0) + (r["status"] in (model.REREVIEW, model.NEW))
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


def project_sections(rows: List[dict], depth: int, ctx: dict) -> List[str]:
    """Every project gets a header and its first PER_PROJECT rows; the rest go into `N more in X ›`."""
    lines: List[str] = []
    for proj in _project_order(rows):
        prs = [r for r in rows if _project(r) == proj]
        lines.append(item(f"{proj.upper()} · {plural(len(prs), 'PR')}", depth, **HEADER))
        for r in prs[:PER_PROJECT]:
            lines.extend(pr_lines(r, depth, ctx))
        rest = prs[PER_PROJECT:]
        if rest:
            lines.append(item(f"{len(rest)} more in {proj.upper()} ›", depth, color=GREY))
            lines.extend(_paged_rows(rest, depth + 1, ctx))
    return lines


def run_lines(records: Dict[str, dict], views: Dict[str, dict], ctx: dict) -> List[str]:
    if not records:
        return []
    lines = ["---", item("Reviews by chip", 0, **HEADER)]
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


def render(inbox_all: Optional[dict], records: Dict[str, dict], views: Dict[str, dict], cfg: dict,
           plugin: str, version: str, newer: Optional[str] = None, error: Optional[str] = None,
           now: Optional[float] = None) -> List[str]:
    now = time.time() if now is None else now
    rows = (inbox_all or {}).get("rows", [])
    visible = [r for r in rows if not r["draft"] and r["status"] != model.APPROVED]
    hidden = [r for r in rows if r["draft"] or r["status"] == model.APPROVED]
    fresh = [r for r in visible if r["status"] == model.REREVIEW or not r.get("stale")]
    older = [r for r in visible if r["status"] != model.REREVIEW and r.get("stale")]
    count = sum(1 for r in fresh if r["status"] in (model.REREVIEW, model.NEW))
    runs_by_label: Dict[str, dict] = {}
    for key, rec in records.items():
        runs_by_label.setdefault(rec["label"], {})[rec["skill"]] = (rec, views[key])
    style = cfg.get("status_style", "dots")
    ctx = {"plugin": plugin, "skills": cfg["skills"], "runs_by_label": runs_by_label, "style": style}

    title = "!" if error else (str(count) if count else "")
    lines = [item(title, 0, templateImage=icon_b64()), "---"]
    if newer:
        lines.append(item(f"Update available: v{newer} — Update now", 0, **symbol("arrow.up.circle.fill", "#FF9500"),
                          color="#FF9500", **action(plugin, "update")))
    if error:
        lines.append(item(f"Could not refresh: {error[:90]}", 0, sfimage="exclamationmark.triangle", color="#FF3B30"))
    for message in cfg.get("errors", [])[:1]:
        lines.append(item(f"Config: {message[:90]} (using defaults)", 0, sfimage="gearshape", color="#FF9500"))
    if inbox_all is not None:
        updated = datetime.fromtimestamp(inbox_all.get("fetched_at", now)).strftime("%H:%M")
        lines.append(item(f"Pull requests · {len(visible)} open · updated {updated}", 0, color=GREY, size="12"))
    lines.append(item("Refresh now", 0, sfimage="arrow.clockwise", **action(plugin, "swiftbar", "--force")))
    if inbox_all is not None:
        lines.append("---")
        if not visible:
            lines.append(item("Nothing waiting for your review", 0, color=GREY))
        elif style == "emoji":
            lines.append(item(LEGEND, 0, **HEADER))
        lines.extend(project_sections(fresh, 0, ctx))
        if older:
            lines.append(item(f"Older than 30 days · {plural(len(older), 'PR')}", 0, sfimage="clock", color=GREY))
            lines.extend(pr_pages(older, 1, ctx))
    lines.extend(run_lines(records, views, ctx))
    lines.append("---")
    if hidden:
        lines.append(item(f"Show approved & drafts ({len(hidden)})", 0, sfimage="eye.slash"))
        lines.extend(pr_pages(hidden, 1, ctx))
    lines.append(item("Settings", 0, sfimage="gearshape"))
    lines.append(item("Status style", 1, sfimage="paintpalette"))
    for value, label in STYLES:
        checked = {"checked": "true"} if value == style else {}
        lines.append(item(label, 2, **checked, **action(plugin, "config", "set", "status_style", value)))
    lines.append(item("Open config", 1, sfimage="doc.text", **action(plugin, "config", "open", refresh=False)))
    lines.append(item("Reinstall", 1, sfimage="arrow.triangle.2.circlepath", **action(plugin, "install")))
    lines.append(item("Check for updates", 1, sfimage="arrow.down.circle", **action(plugin, "update", "--check")))
    lines.append(item("Open chip on GitHub", 1, href=f"https://github.com/{updates.REPO}", sfimage="link"))
    lines.append(item(f"About chip v{version}", 1, disabled="true"))
    return lines


def build_menu(plugin: str, force: bool = False, fetch_runner=None, runner=None,
               now: Optional[float] = None) -> str:
    """One refresh: inbox (3-min cache), run states, release check, notifications, menu text."""
    now = time.time() if now is None else now
    cfg = config.load()
    inbox_all, error = store.load_all(fetch_runner or fetch.run_gh_graphql, force)
    runs_path = store.cache_dir() / "runs.json"
    records = runs.load(runs_path)
    agents = runs.fetch_agents(runner) if records else {}
    if runs.observe(records, agents, now):
        runs.save(runs_path, records)
    views = {key: runs.view(rec, agents.get(rec["id"]), now) for key, rec in records.items()}
    latest = updates.latest_release(store.cache_dir() / "update.json", runner, now)
    newer = latest if latest and updates.is_newer(latest, __version__) else None
    if inbox_all is not None:
        visible = model.visible_view(inbox_all)["rows"]
        notify_path = store.cache_dir() / "notify.json"
        current = notify.snapshot(visible, views, newer)
        notify.send(notify.diff(notify.load(notify_path), current, visible, records), runner)
        notify.save(notify_path, current)
    return "\n".join(render(inbox_all, records, views, cfg, plugin, __version__, newer, error, now))
