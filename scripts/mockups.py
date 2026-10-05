"""Draw the README images (dark mode, made-up data): python3 scripts/mockups.py

docs/images/menu-review.svg   Review requests tab + a PR submenu
docs/images/menu-mine.svg     My pull requests tab + a PR submenu (address review, feature session, actions)
docs/images/review-rounds.svg How a review runs: worktree, background session, rounds
docs/images/menu-bar.svg      Menu bar states, Settings › Menu bar, a notification
docs/images/arrange-projects.svg  The Projects submenu: drag to reorder, tick to show
"""
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
SANS = "-apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Segoe UI', Helvetica, Arial, sans-serif"
MONO = "'SF Mono', SFMono-Regular, Menlo, Consolas, monospace"
BG, PANEL, LINE, TEXT, GREY, BLUE = "#1e1e1e", "#2a2a2a", "#3a3a3a", "#e6e6e6", "#8e8e93", "#2459d4"
DOT = {"orange": "#ff9f0a", "green": "#30d158", "grey": "#d0d0d0", "blue": "#0a84ff", "red": "#ff453a",
       "yellow": "#ffd60a"}
ROW = 30
MARK = (ROOT / "chip" / "assets" / "github-mark.svg").read_text().split(' d="', 1)[1].split('"', 1)[0]


class Svg:
    def __init__(self, width):
        self.width, self.out = width, []

    def add(self, s):
        self.out.append(s)

    def text(self, x, y, s, size=15, color=TEXT, font=SANS, anchor="start", weight="normal"):
        self.add(f'<text x="{x}" y="{y}" font-family="{font}" font-size="{size}" fill="{color}" '
                 f'font-weight="{weight}" text-anchor="{anchor}">{escape(s)}</text>')

    def rect(self, x, y, w, h, fill, rx=8, stroke=None):
        extra = f' stroke="{stroke}"' if stroke else ""
        self.add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}"{extra}/>')

    def chevron(self, x, y, color=TEXT):
        self.add(f'<path d="M{x} {y - 6} l5 5 l-5 5" fill="none" stroke="{color}" stroke-width="1.8" '
                 f'stroke-linecap="round" stroke-linejoin="round"/>')

    def dot(self, x, y, color, r=7):
        self.add(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{color}"/>')

    def sep(self, x1, x2, y):
        self.add(f'<line x1="{x1}" y1="{y}" x2="{x2}" y2="{y}" stroke="{LINE}" stroke-width="1"/>')

    def mark(self, x, y, scale=1.15, color=TEXT):
        self.add(f'<path d="{MARK}" fill="{color}" transform="translate({x} {y}) scale({scale})"/>')

    def icon(self, kind, x, y, color=TEXT):
        s = f'fill="none" stroke="{color}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"'
        shapes = {
            "refresh": f'<path d="M{x+13} {y-1} a6.5 6.5 0 1 1 -2 -5 M{x+12} {y-10} v4.5 h-4.5" {s}/>',
            "search": f'<circle cx="{x+6}" cy="{y-5}" r="5" {s}/><path d="M{x+10} {y-1} l4 4" {s}/>',
            "grid": "".join(f'<rect x="{x+dx}" y="{y-11+dy}" width="5" height="5" rx="1" {s}/>'
                            for dx in (1, 8) for dy in (0, 7)),
            "clock": f'<circle cx="{x+7}" cy="{y-5}" r="6.5" {s}/><path d="M{x+7} {y-9} v4 l3 2" {s}/>',
            "eyeslash": f'<path d="M{x} {y-5} q7 -8 14 0 q-7 8 -14 0" {s}/><path d="M{x+1} {y-12} l12 13" {s}/>',
            "bell": f'<path d="M{x+2} {y} h10 l-1.5 -2 v-4 a3.5 3.5 0 0 0 -7 0 v4 z M{x+5.5} {y+2} h3" {s}/>',
            "gear": f'<circle cx="{x+7}" cy="{y-5}" r="2.5" {s}/><circle cx="{x+7}" cy="{y-5}" r="6.5" {s} '
                    f'stroke-dasharray="3 2"/>',
            "play": f'<path d="M{x+3} {y-11} l9 6 l-9 6 z" fill="{color}"/>',
            "link": f'<path d="M{x+2} {y-2} l10 -10 M{x+6} {y-12} h6 v6" {s}/>',
            "copy": f'<rect x="{x+4}" y="{y-12}" width="8" height="10" rx="1.5" {s}/><path d="M{x+2} {y-9} v9 h7" {s}/>',
            "eye": f'<path d="M{x} {y-5} q7 -8 14 0 q-7 8 -14 0" {s}/><circle cx="{x+7}" cy="{y-5}" r="2" {s}/>',
            "check": f'<circle cx="{x+7}" cy="{y-5}" r="6.5" {s}/><path d="M{x+4} {y-5} l2 2 l4 -4" {s}/>',
            "x": f'<circle cx="{x+7}" cy="{y-5}" r="6.5" {s}/><path d="M{x+4.5} {y-7.5} l5 5 M{x+9.5} {y-7.5} l-5 5" {s}/>',
            "bubble": f'<path d="M{x+1} {y-11} h12 v8 h-7 l-3 3 v-3 h-2 z" {s}/>',
            "terminal": f'<rect x="{x}" y="{y-12}" width="14" height="11" rx="2" {s}/><path d="M{x+3} {y-9} l3 2 l-3 2" {s}/>',
            "merge": f'<circle cx="{x+3}" cy="{y-11}" r="1.8" {s}/><circle cx="{x+3}" cy="{y}" r="1.8" {s}/>'
                     f'<circle cx="{x+12}" cy="{y-5}" r="1.8" {s}/><path d="M{x+3} {y-9} v7 M{x+3} {y-8} q0 3 7 3" {s}/>',
            "pencil": f'<path d="M{x+2} {y} l1 -4 l8 -8 l3 3 l-8 8 z" {s}/>',
            "bellplus": f'<path d="M{x+2} {y} h10 l-1.5 -2 v-4 a3.5 3.5 0 0 0 -7 0 v4 z" {s}/>',
        }
        self.add(shapes[kind])

    def row(self, x, y, label, kind=None, arrow=False, color=TEXT, right=0, check=False, size=15):
        if check:
            self.text(x - 2, y, "✓", 15)
        if kind:
            self.icon(kind, x + 18, y, color if color != GREY else TEXT)
        self.text(x + (44 if kind else 18), y, label, size, color)
        if arrow:
            self.chevron(right - 26, y - 5)

    def pr(self, x, y, right, color, cols, highlight=False, dot=True):
        if highlight:
            self.rect(x - 2, y - 20, right - x - 6, 28, BLUE, rx=6)
        fg = "#ffffff" if highlight else TEXT
        if dot:
            self.dot(x + 26, y - 5, color)
        for col, value in cols:
            self.text(x + col, y, value, 13.5, fg, MONO)
        self.chevron(right - 26, y - 5, fg)

    def svg(self, height):
        head = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.width}" height="{height}" '
                f'viewBox="0 0 {self.width} {height}">'
                f'<rect width="{self.width}" height="{height}" rx="14" fill="#0d1117"/>')
        return head + "\n" + "\n".join(self.out) + "\n</svg>\n"


def menubar(c, x, title, clock="Sun 4 Oct  17:29", ring=False, attention=False, width=None):
    c.add(f'<rect x="0" y="0" width="{c.width}" height="38" rx="14" fill="#1c1c1e"/>')
    w = width or (40 + 9 * len(title))
    c.rect(x + 12, 6, w, 26, "#3a3a3c", rx=7)
    c.mark(x + 21, 10)
    if attention:
        c.dot(x + 38, 11, DOT["yellow"], r=3.5)
    c.text(x + 46, 25, title, 15)
    c.text(c.width - 24, 25, clock, 14, anchor="end")


def panel_top(c, mx, mw, top, tabs, active, search=True):
    c.rect(mx + 14, top + 18, mw - 28, 30, PANEL, rx=7)
    half = (mw - 32) / 2
    c.rect(mx + 16 + (0 if active == 0 else half), top + 20, half, 26, "#4a4a4a", rx=6)
    for i, label in enumerate(tabs):
        c.text(mx + 16 + half / 2 + i * half, top + 38, label, 14.5, TEXT if i == active else GREY, anchor="middle")
    y = top + 76
    c.text(mx + 18, y, "Updated 17:29", 13, GREY)
    y += ROW
    c.row(mx, y, "Refresh now", "refresh")
    y += 14
    c.sep(mx + 12, mx + mw - 12, y)
    y += 10
    if search:
        c.rect(mx + 12, y, mw - 24, 30, PANEL, stroke=LINE)
        c.icon("search", mx + 22, y + 21, GREY)
        c.text(mx + 44, y + 20, "Search pull requests", 14.5, GREY)
        y += 54
    c.row(mx, y, "Projects", "grid", arrow=True, right=mx + mw)
    y += 14
    c.sep(mx + 12, mx + mw - 12, y)
    return y + 26


def submenu(c, sx, sy, sw, items):
    """items: ("dim", text) | ("sep",) | (icon, text) | ("head", text)"""
    height = sum(16 if it[0] == "sep" else ROW for it in items) + 20
    c.rect(sx, sy, sw, height, BG, rx=12, stroke="#444")
    y = sy + 30
    for it in items:
        if it[0] == "sep":
            c.sep(sx + 12, sx + sw - 12, y - 12)
            y += 16
            continue
        if it[0] in ("dim", "head"):
            c.text(sx + 20, y, it[1], 13.5 if it[0] == "head" else 14.5, GREY)
        else:
            c.icon(it[0], sx + 18, y)
            c.text(sx + 44, y, it[1], 15)
        y += ROW
    return sy + height


def footer(c, mx, mw, y, extra=()):
    for kind, label in extra:
        c.row(mx, y, label, kind, arrow=True, right=mx + mw)
        y += ROW
    c.row(mx, y, "Recent notifications", "bell", arrow=True, right=mx + mw); y += ROW
    c.row(mx, y, "Settings", "gear", arrow=True, right=mx + mw)
    y += 14; c.sep(mx + 12, mx + mw - 12, y); y += 26
    c.row(mx, y, "Open at Login", check=True); y += ROW
    c.text(mx + 18, y, "Quit GitHubBar", 15); c.text(mx + mw - 20, y, "⌘Q", 14, GREY, anchor="end")
    return y


def menu_review():
    c = Svg(1180)
    mx, mw = 24, 700
    menubar(c, mx, "22 · ⚠8")
    top = 50
    panel = len(c.out)
    y = panel_top(c, mx, mw, top, ["Review requests · 22 / 30", "My pull requests · 8 / 72"], 0)
    cols = lambda n, s, t, a: [(42, n), (106, s), (200, t), (540, a)]
    rows = [
        ("head", "API · 17 PRs"),
        ("pr", "green", cols("#2124", "New", "feat(auth): add login with Google…", "alice"), True),
        ("pr", "blue", cols("#2123", "Reviewing", "fix(cart): keep discounts after u…", "alice"), False),
        ("pr", "orange", cols("#2118", "Re-review", "ABC-123 feat(search): typo-tole…", "bob"), False),
        ("pr", "orange", cols("#2102", "Re-review", "feat(export): download orders a…", "bob"), False),
        ("more", "13 more in API ›"),
        ("head", "SHOPBOX-API · 2 PRs"),
        ("pr", "green", cols("#272", "New", "refactor(events): sync a date ra…", "carol"), False),
        ("pr", "grey", cols("#61", "Commented", "fix(contacts): backfill country…", "erin"), False),
    ]
    hy = None
    for r in rows:
        if r[0] == "head":
            c.text(mx + 42, y, r[1], 12.5, GREY); y += 26
        elif r[0] == "more":
            c.text(mx + 42, y, r[1], 15, GREY); c.chevron(mx + mw - 26, y - 5); y += ROW
        else:
            c.pr(mx + 4, y, mx + mw, DOT[r[1]], r[2], r[3])
            hy = y if r[3] else hy
            y += ROW
    c.row(mx, y, "Older than 30 days · 7 PRs", "clock", arrow=True, color=GREY, right=mx + mw)
    y += 14; c.sep(mx + 12, mx + mw - 12, y); y += 26
    c.text(mx + 18, y, "Reviews by GitHubBar", 12.5, GREY); y += ROW
    c.dot(mx + 26, y - 5, DOT["blue"])
    c.text(mx + 42, y, "api#2123 · Full review · running 3m", 15); c.chevron(mx + mw - 26, y - 5)
    y += 14; c.sep(mx + 12, mx + mw - 12, y); y += 26
    y = footer(c, mx, mw, y, [("eyeslash", "Show approved & drafts (7)")])
    sub_end = submenu(c, mx + mw - 6, hy - 30, 456, [
        ("dim", "api#2124"), ("dim", "feat(auth): add login with Google"),
        ("dim", "New · by alice · opened 2 hours ago"), ("dim", "+120 −34 · 8 files · base dev"), ("sep",),
        ("play", 'Run "Full review"'), ("play", 'Run "/review (project)"'), ("sep",),
        ("check", "Approve…"), ("x", "Request changes…"), ("bubble", "Comment…"), ("sep",),
        ("link", "Open on GitHub"), ("copy", "Copy link")])
    height = max(y + 38, sub_end + 20)
    c.out.insert(panel, f'<rect x="{mx}" y="{top}" width="{mw}" height="{y + 22 - top}" rx="12" fill="{BG}" stroke="#444"/>')
    return c.svg(height)


def menu_mine():
    c = Svg(1180)
    mx, mw = 24, 700
    menubar(c, mx, "22 · ⚠8")
    top = 50
    panel = len(c.out)
    y = panel_top(c, mx, mw, top, ["Review requests · 22 / 30", "My pull requests · 8 / 72"], 1)
    cols = lambda n, s, t, a: [(42, n), (106, s), (200, t), (500, a)]
    rows = [
        ("head", "API · 6 PRs"),
        ("pr", "red", cols("#2130", "Changes", "feat(billing): prorate plan ch…", "bob ✗ carol ✓"), True),
        ("pr", "red", cols("#2127", "CI failed", "fix(webhooks): retry on 5xx re…", "→ bob"), False),
        ("pr", "orange", cols("#2119", "Conflict", "chore(deps): bump the test ru…", "carol 💬"), False),
        ("pr", "grey", cols("#2111", "2 threads", "feat(api): paginate the order…", "bob 💬"), False),
        ("pr", "green", cols("#2105", "Approved", "docs: explain the retry polic…", "carol ✓"), False),
        ("more", "1 more in API ›"),
        ("head", "SHOPBOX-API · 2 PRs"),
        ("pr", "grey", cols("#280", "Waiting", "feat(box): weekly digest email", "→ dave, erin"), False),
        ("pr", "grey", cols("#276", "Draft", "spike: new pricing table", "—"), False),
    ]
    hy = None
    for r in rows:
        if r[0] == "head":
            c.text(mx + 42, y, r[1], 12.5, GREY); y += 26
        elif r[0] == "more":
            c.text(mx + 42, y, r[1], 15, GREY); c.chevron(mx + mw - 26, y - 5); y += ROW
        else:
            c.pr(mx + 4, y, mx + mw, DOT[r[1]], r[2], r[3])
            hy = y if r[3] else hy
            y += ROW
    y += 4; c.sep(mx + 12, mx + mw - 12, y); y += 26
    y = footer(c, mx, mw, y)
    sub_end = submenu(c, mx + mw - 6, hy - 30, 456, [
        ("dim", "api#2130"), ("dim", "feat(billing): prorate plan changes"), ("dim", "Changes requested · opened 3 days ago"),
        ("dim", "Reviews: bob ✗ · carol ✓"), ("sep",),
        ("play", 'Run "Address review"'), ("sep",),
        ("head", "Feature session · 2026-10-01 · found on feat/prorate"),
        ("head", "“add proration when a plan changes mid-cycle”"),
        ("play", "Address review in feature session"), ("terminal", "Open feature session"),
        ("link", "Link another session…"), ("sep",),
        ("bellplus", "Re-request review (bob)"), ("sep",),
        ("pencil", "Convert to draft"), ("bubble", "Comment…"), ("x", "Close PR…"), ("sep",),
        ("link", "Open on GitHub"), ("copy", "Copy link")])
    height = max(y + 38, sub_end + 20)
    c.out.insert(panel, f'<rect x="{mx}" y="{top}" width="{mw}" height="{y + 22 - top}" rx="12" fill="{BG}" stroke="#444"/>')
    return c.svg(height)


def review_rounds():
    c = Svg(1180)
    c.text(40, 50, "What Run does", 20, TEXT, weight="bold")
    steps = [
        ("1", "Find your clone", "your code folders, or", "a clone in chip's cache"),
        ("2", "Check the PR out", "its own git worktree, with", "your settings, .env, vendor"),
        ("3", "Pick the review", "your skill, the repo's", "/review, or the built-in"),
        ("4", "Run in background", "claude --bg, read-only;", "the row turns 🔵 Reviewing"),
        ("5", "Read the result", "✅ Reviewed + notification;", "View session opens it"),
    ]
    x = 40
    for n, title, l1, l2 in steps:
        c.rect(x, 80, 204, 120, PANEL, rx=12, stroke=LINE)
        c.dot(x + 24, 106, BLUE, r=12)
        c.text(x + 24, 111, n, 13, "#ffffff", anchor="middle", weight="bold")
        c.text(x + 44, 111, title, 15, TEXT, weight="bold")
        c.text(x + 16, 146, l1, 13, GREY)
        c.text(x + 16, 168, l2, 13, GREY)
        if n != "5":
            c.add(f'<path d="M{x + 208} 140 h14 m-6 -6 l6 6 l-6 6" fill="none" stroke="{GREY}" stroke-width="1.8"/>')
        x += 228
    c.text(40, 260, "Rounds: one session per review button", 20, TEXT, weight="bold")
    lanes = [("Round 1", "Run \"Full review\"", "new session abc123", "findings: 3 bugs, 1 test gap"),
             ("Round 2", "Continue review (round 2)", "same session abc123", "checks each finding: fixed / answered / open,\nthen reviews only the new commits"),
             ("Round 3", "Continue review (round 3)", "same session abc123", "…")]
    y = 290
    for i, (name, button, session, result) in enumerate(lanes):
        c.rect(40, y, 1100, 64, PANEL, rx=12, stroke=LINE)
        c.text(60, y + 38, name, 15, TEXT, weight="bold")
        c.icon("play", 150, y + 38)
        c.text(176, y + 38, button, 14.5)
        c.text(440, y + 38, session, 13.5, DOT["blue"], MONO)
        for j, part in enumerate(result.split("\n")):
            c.text(680, y + 30 + 18 * j if "\n" in result else y + 38, part, 13.5, GREY)
        if i < len(lanes) - 1:
            c.text(60, y + 86, "new commits pushed → the round resolves → the button becomes Continue", 12.5, GREY)
        y += 100
    c.text(40, y + 6, "Your own PRs: Address review in feature session continues the Claude Code session where you built the PR.", 13.5, GREY)
    return c.svg(y + 36)


def menu_bar():
    c = Svg(1180)
    c.text(40, 44, "The menu bar icon", 20, TEXT, weight="bold")
    states = [("Counts", "19 · ⚠8", False, False), ("Review running", "19 · ⚠8", True, False),
              ("Review needs you", "19 · ⚠8", False, True), ("Badges on", "19 · ⚠8 🔵1 🟡1", False, False),
              ("Plain icon", "", False, False)]
    y = 70
    for label, title, ring, attention in states:
        c.rect(40, y, 300, 44, "#1c1c1e", rx=10)
        c.rect(52, y + 9, 50 + 9 * len(title), 26, "#3a3a3c", rx=7)
        c.mark(61, y + 13)
        if ring:  # the spinning ring, frozen in the picture
            c.add(f'<circle cx="70.2" cy="{y + 22.2}" r="12" fill="none" stroke="{TEXT}" stroke-width="1.8" '
                  f'stroke-linecap="round" stroke-dasharray="20 56"/>')
        if attention:
            c.dot(78, y + 14, DOT["yellow"], r=3.5)
        c.text(86, y + 28, title, 15)
        c.text(360, y + 28, label, 14.5, GREY)
        y += 56
    # Settings › Menu bar
    sx, sy = 560, 64
    submenu(c, sx, sy, 300, [("gear", "Status style"), ("gear", "Menu bar"), ("dim", "Open config"),
                             ("dim", "Check for updates"), ("dim", "About GitHubBar v0.1.7")])
    c.rect(sx + 296, sy + 46, 300, 110, BG, rx=12, stroke="#444")
    for i, (on, label) in enumerate([(True, "Show counts"), (False, "Show review badges"), (True, "Animate while reviewing")]):
        if on:
            c.text(sx + 312, sy + 78 + 30 * i, "✓", 15)
        c.text(sx + 334, sy + 78 + 30 * i, label, 15)
    # notification
    ny = 400
    c.text(40, ny, "Notifications", 20, TEXT, weight="bold")
    c.rect(40, ny + 20, 520, 76, "#2c2c2e", rx=16, stroke=LINE)
    c.rect(56, ny + 36, 40, 40, "#3a3a3c", rx=9)
    c.mark(64, ny + 44, scale=1.5)
    c.text(110, ny + 52, "GitHubBar", 14.5, TEXT, weight="bold")
    c.text(110, ny + 74, "bob requested changes on api#2130 — feat(billing): prorate…", 13.5, GREY)
    c.text(580, ny + 52, "Click: opens the PR (or the review session).", 14, GREY)
    c.text(580, ny + 74, "The last 10 stay under Recent notifications ›.", 14, GREY)
    return c.svg(ny + 120)


def arrange_projects():
    c = Svg(1180)
    c.text(40, 44, "Projects: drag to reorder, tick to show", 20, TEXT, weight="bold")
    # the main menu's edge with Projects highlighted
    mx, mw = 40, 420
    c.rect(mx, 64, mw, 300, BG, rx=12, stroke="#444")
    c.rect(mx + 12, 84, mw - 24, 30, PANEL, stroke=LINE)
    c.icon("search", mx + 22, 105, GREY)
    c.text(mx + 44, 104, "Search pull requests", 14.5, GREY)
    c.rect(mx + 6, 124, mw - 12, 28, BLUE, rx=6)
    c.icon("grid", mx + 18, 144, "#ffffff")
    c.text(mx + 44, 144, "Projects", 15, "#ffffff")
    c.chevron(mx + mw - 26, 139, "#ffffff")
    c.sep(mx + 12, mx + mw - 12, 166)
    y = 192
    for head, rows in (("API · 9 PRs", ["#2124  feat(auth): add login…", "#2123  fix(cart): keep disco…"]),
                       ("SHOP · 4 PRs", ["#272   refactor(events): sync…"]),
                       ("MAILER · 2 PRs", ["#58    feat(export): downloa…"])):
        c.text(mx + 42, y, head, 12.5, GREY); y += 24
        for text in rows:
            c.dot(mx + 26, y - 5, DOT["green"]); c.text(mx + 42, y, text, 13.5, TEXT, MONO); y += 26
    # the Projects submenu with the list
    sx, sy, sw = mx + mw - 6, 112, 300
    names = [("api", True, False), ("shop", True, True), ("mailer", True, False), ("billing", False, False),
             ("docs", True, False)]
    c.rect(sx, sy, sw, 64 + 30 * len(names), BG, rx=12, stroke="#444")
    c.text(sx + 34, sy + 30, "Show all", 15)
    c.sep(sx + 12, sx + sw - 12, sy + 44)
    ry = sy + 74
    for name, on, dragging in names:
        if dragging:
            c.rect(sx + 6, ry - 20, sw - 12, 28, BLUE, rx=6)
        color = "#ffffff" if dragging else TEXT
        box = "#0a84ff" if on else "none"
        c.add(f'<rect x="{sx + 20}" y="{ry - 15}" width="14" height="14" rx="3.5" fill="{box}" '
              f'stroke="{GREY if not on else box}" stroke-width="1.2"/>')
        if on:
            c.add(f'<path d="M{sx + 23} {ry - 8} l3 3 l5 -6" fill="none" stroke="#ffffff" stroke-width="1.8" '
                  f'stroke-linecap="round" stroke-linejoin="round"/>')
        c.text(sx + 44, ry, name, 15, color)
        c.text(sx + sw - 30, ry, "≡", 15, color if dragging else "#5a5a5e")
        ry += 30
    c.add(f'<path d="M{sx + sw + 16} {sy + 104} v-26 m-6 6 l6 -6 l6 6" fill="none" stroke="{DOT["blue"]}" '
          f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>')
    c.text(sx + sw + 30, sy + 92, "drag shop above api", 13, DOT["blue"])
    c.text(sx + sw + 30, sy + 186, "untick to hide billing", 13, GREY)
    c.add(f'<path d="M{sx + sw + 24} {sy + 182} h-14" fill="none" stroke="{GREY}" stroke-width="1.5"/>')
    c.text(40, 400, "Changes apply at once and the menu stays open: the PR lists behind the submenu reorder and hide",
           13.5, GREY)
    c.text(40, 422, "while you drag. One order for both tabs; projects you have not placed follow, busiest first.",
           13.5, GREY)
    return c.svg(446)


def main():
    out = ROOT / "docs" / "images"
    out.mkdir(parents=True, exist_ok=True)
    for name, draw in (("menu-review", menu_review), ("menu-mine", menu_mine),
                       ("review-rounds", review_rounds), ("menu-bar", menu_bar),
                       ("arrange-projects", arrange_projects)):
        (out / f"{name}.svg").write_text(draw())
        print(out / f"{name}.svg")


if __name__ == "__main__":
    main()
