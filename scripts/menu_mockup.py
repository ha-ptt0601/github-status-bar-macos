"""Draw docs/images/menu.svg: the GitHubBar menu (dark mode) for the README. Run: python3 scripts/menu_mockup.py"""
from pathlib import Path
from xml.sax.saxutils import escape

SANS = "-apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Segoe UI', Helvetica, Arial, sans-serif"
MONO = "'SF Mono', SFMono-Regular, Menlo, Consolas, monospace"
BG, PANEL, LINE, TEXT, GREY, BLUE = "#1e1e1e", "#2a2a2a", "#3a3a3a", "#e6e6e6", "#8e8e93", "#2459d4"
DOT = {"orange": "#ff9f0a", "green": "#30d158", "grey": "#d0d0d0", "blue": "#0a84ff"}
ROW = 30

out = []


def text(x, y, s, size=15, color=TEXT, font=SANS, weight="normal", anchor="start"):
    out.append(f'<text x="{x}" y="{y}" font-family="{font}" font-size="{size}" fill="{color}" '
               f'font-weight="{weight}" text-anchor="{anchor}">{escape(s)}</text>')


def chevron(x, y, color=TEXT):
    out.append(f'<path d="M{x} {y - 6} l5 5 l-5 5" fill="none" stroke="{color}" stroke-width="1.8" '
               f'stroke-linecap="round" stroke-linejoin="round"/>')


def dot(x, y, color):
    out.append(f'<circle cx="{x}" cy="{y}" r="7" fill="{color}"/>')


def sep(x1, x2, y):
    out.append(f'<line x1="{x1}" y1="{y}" x2="{x2}" y2="{y}" stroke="{LINE}" stroke-width="1"/>')


def icon(kind, x, y, color=TEXT):
    """Small line icons in the style of SF Symbols."""
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
        "copy": f'<rect x="{x+4}" y="{y-12}" width="8" height="10" rx="1.5" {s}/>'
                f'<path d="M{x+2} {y-9} v9 h7" {s}/>',
        "eye": f'<path d="M{x} {y-5} q7 -8 14 0 q-7 8 -14 0" {s}/><circle cx="{x+7}" cy="{y-5}" r="2" {s}/>',
    }
    out.append(shapes[kind])


def plain(x, y, label, kind=None, arrow=False, color=TEXT, right=0, check=False):
    if check:
        text(x - 2, y, "✓", 15)
    if kind:
        icon(kind, x + 18, y)
    text(x + (44 if kind else 18), y, label, 15, color)
    if arrow:
        chevron(right - 26, y - 5)


def pr_row(x, y, color, number, status, title, author, right, highlight=False):
    if highlight:
        out.append(f'<rect x="{x - 2}" y="{y - 20}" width="{right - x - 6}" height="28" rx="6" fill="{BLUE}"/>')
    dot(x + 26, y - 5, color)
    fg = "#ffffff" if highlight else TEXT
    # One <text> per column at a fixed x, so columns line up whatever font the viewer has.
    for col, value in ((42, number), (106, status), (200, title), (540, author)):
        text(x + col, y, value, 13.5, fg, MONO)
    chevron(right - 26, y - 5, fg)


def header(x, y, label):
    text(x + 42, y, label, 12.5, GREY)


# --- canvas -----------------------------------------------------------------------------
W, H = 1180, "__H__"              # height is filled in once the menu is laid out
MX, MW = 24, 700                  # main menu
SX, SW = MX + MW - 6, 450         # PR submenu
out.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">')
out.append(f'<rect width="{W}" height="{H}" rx="14" fill="#0d1117"/>')

# menu bar strip with the GitHubBar item
out.append(f'<rect x="0" y="0" width="{W}" height="38" rx="14" fill="#1c1c1e"/>')
out.append(f'<rect x="{MX + 12}" y="6" width="118" height="26" rx="7" fill="#3a3a3c"/>')
mark = Path(__file__).resolve().parents[1] / "chip" / "assets" / "github-mark.svg"
path = mark.read_text().split(' d="', 1)[1].split('"', 1)[0]  # the 16x16 GitHub mark
out.append(f'<path d="{path}" fill="{TEXT}" transform="translate({MX + 21} 10) scale(1.15)"/>')
text(MX + 46, 25, "22 · ⚠8", 15)
text(W - 24, 25, "Sun 4 Oct  17:29", 14, TEXT, anchor="end")

# main menu panel
top = 50
out.append(f'<rect x="{MX}" y="{top}" width="{MW}" height="__PANEL__" rx="12" fill="{BG}" stroke="#444" />')
y = top + 18
# tab bar
out.append(f'<rect x="{MX + 14}" y="{y}" width="{MW - 28}" height="30" rx="7" fill="{PANEL}"/>')
out.append(f'<rect x="{MX + 16}" y="{y + 2}" width="{(MW - 32) / 2}" height="26" rx="6" fill="#4a4a4a"/>')
text(MX + 16 + (MW - 32) / 4, y + 20, "Review requests · 22 / 30", 14.5, TEXT, anchor="middle")
text(MX + 16 + 3 * (MW - 32) / 4, y + 20, "My pull requests · 8 / 72", 14.5, GREY, anchor="middle")
y += 58
text(MX + 18, y, "Updated 17:29", 13, GREY)
y += ROW
plain(MX, y, "Refresh now", "refresh")
y += 14; sep(MX + 12, MX + MW - 12, y); y += 10
out.append(f'<rect x="{MX + 12}" y="{y}" width="{MW - 24}" height="30" rx="8" fill="{PANEL}" stroke="#3a3a3a"/>')
icon("search", MX + 22, y + 21, GREY)
text(MX + 44, y + 20, "Search pull requests", 14.5, GREY)
y += 54
plain(MX, y, "Projects", "grid", arrow=True, right=MX + MW)
y += 14; sep(MX + 12, MX + MW - 12, y); y += 26

rows = [
    ("header", "API · 17 PRs"),
    ("pr", "orange", "#2079", "Re-review", "ABC-123 feat(auth): add login with Goo…", "alice", True),
    ("pr", "orange", "#2080", "Re-review", "ABC-123 feat(cart): keep discounts af…", "alice", False),
    ("pr", "green", "#2094", "New", "fix(api): handle an empty webhook pay…", "bob", False),
    ("more", "12 more in API ›"),
    ("header", "SHOPBOX-API · 3 PRs"),
    ("pr", "blue", "#261", "Reviewing", "feat(box): pick items from any pool…", "alice", False),
    ("pr", "green", "#272", "New", "refactor(events): sync a date range…", "carol", False),
    ("header", "MAILER-API · 2 PRs"),
    ("pr", "green", "#58", "New", "feat(export): download orders as CSV…", "bob", False),
    ("pr", "grey", "#61", "Commented", "fix(contacts): backfill country cod…", "erin", False),
]
highlight_y = None
for r in rows:
    if r[0] == "header":
        header(MX, y, r[1]); y += 26
    elif r[0] == "more":
        text(MX + 42, y, r[1], 15, GREY); chevron(MX + MW - 26, y - 5); y += ROW
    else:
        _, color, number, status, title, author, hl = r
        pr_row(MX + 4, y, DOT[color], number, status, title, author, MX + MW, hl)
        if hl:
            highlight_y = y
        y += ROW
plain(MX, y, "Older than 30 days · 7 PRs", "clock", arrow=True, color=GREY, right=MX + MW)
y += 14; sep(MX + 12, MX + MW - 12, y); y += 26
text(MX + 18, y, "Reviews by GitHubBar", 12.5, GREY); y += ROW
dot(MX + 26, y - 5, DOT["blue"])
text(MX + 42, y, "shopbox-api#261 · /review (project) · running 3m", 15); chevron(MX + MW - 26, y - 5)
y += 14; sep(MX + 12, MX + MW - 12, y); y += 26
plain(MX, y, "Show approved & drafts (7)", "eyeslash", arrow=True, right=MX + MW); y += ROW
plain(MX, y, "Recent notifications", "bell", arrow=True, right=MX + MW); y += ROW
plain(MX, y, "Settings", "gear", arrow=True, right=MX + MW)
y += 14; sep(MX + 12, MX + MW - 12, y); y += 26
plain(MX, y, "Open at Login", check=True); y += ROW
text(MX + 18, y, "Quit GitHubBar", 15); text(MX + MW - 20, y, "⌘Q", 14, GREY, anchor="end")

# PR submenu next to the highlighted row
sy = highlight_y - 30
items = [
    ("dim", "api#2079"),
    ("dim", "ABC-123 feat(auth): add login with Google"),
    ("dim", "Re-review · by alice · opened 2 days ago"),
    ("dim", "+120 −34 · 8 files · base dev · ABC-123"),
    ("sep", ""),
    ("run", 'Run "Full review"'),
    ("run", 'Run "/review (project)"'),
    ("sep", ""),
    ("link", "Open on GitHub"),
    ("copy", "Copy link"),
]
height = sum(16 if k == "sep" else ROW for k, _ in items) + 20
out.append(f'<rect x="{SX}" y="{sy}" width="{SW}" height="{height}" rx="12" fill="{BG}" stroke="#444"/>')
yy = sy + 30
for kind, label in items:
    if kind == "sep":
        sep(SX + 12, SX + SW - 12, yy - 12); yy += 16; continue
    if kind == "dim":
        text(SX + 20, yy, label, 14.5, GREY)
    else:
        icon({"run": "play", "link": "link", "copy": "copy"}[kind], SX + 18, yy)
        text(SX + 44, yy, label, 15)
    yy += ROW

out.append("</svg>")
panel = y + 22 - top
svg = "\n".join(out).replace("__PANEL__", str(panel)).replace("__H__", str(top + panel + 16))
target = Path(__file__).resolve().parents[1] / "docs" / "images" / "menu.svg"
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(svg + "\n")
print(target)
