# chip menu bar (SwiftBar)

Date: 2026-10-03
Status: approved (design)

## Goal

A GitHub icon in the macOS menu bar lists the PRs waiting for the user's review. The user clicks **▶ Chạy review** on a PR to run `/my-review-skill` on it in a background Claude Code session, and clicks **👁 Xem chi tiết** to watch or continue that session. macOS notifications report new PRs, PRs that need a re-review, finished reviews, and reviews waiting on the user.

## Non-goals

- No automatic reviews. A review starts only when the user clicks ▶ on that PR.
- No fork of claude-status-bar-macos. Background review sessions appear in its Sessions list on their own, because it tracks every Claude Code session.
- No custom popover UI (SwiftBar renders a standard macOS menu).
- No click-through from notifications. `osascript` notifications cannot open a session; the menu does that.

## Pieces

| Piece | Responsibility |
|---|---|
| `swiftbar/chip.3m.sh` | SwiftBar plugin (refresh every 3 min). Runs `chip swiftbar`. It lives in the SwiftBar plugin folder as a symlink to the repo. |
| `chip swiftbar` (`chip/swiftbar.py`) | Prints the SwiftBar menu text: icon line, header, PR sections, chip review runs, and the Refresh item. It also sends the notifications (see below). |
| `chip run <label> [--skill N]` (`chip/runs.py`) | Starts a background review for one PR with the chosen skill and records it. |
| `chip/config.py` | Loads and validates `~/.config/chip/config.json` (skills, work root, permissions), with defaults. |
| `chip attach <label>` / `chip stop <label>` / `chip forget <label>` | Opens `claude attach <id>` in a new Terminal window / runs `claude stop <id>` / runs `claude rm <id>` and drops the record. |
| `~/.cache/chip/runs.json` | `{"<label>|<skill name>": {id, url, repo, skill, started_at}}` for each review chip started. |
| `~/.cache/chip/notify.json` | Snapshot from the previous refresh, used to diff for notifications. |

Every piece reuses the existing inbox code (`fetch`, `model`, `menu.assign_labels`, the 3-minute cache) and `repos.resolve/clone`.

## Menu layout

```
<GitHub template icon> N                       ← N = re-review + new PRs (hidden when 0)
---
Cập nhật 12:05 · 44 PR · ẩn 11 đã approve
↻ Refresh                                       ← chip swiftbar refresh, force fetch
---
Cần re-review (6)
api#2094  ABC-997 fix: Brevo leftovers…  9d
--▶ Chạy review                                 ← chip run api#2094 (terminal=false refresh=true)
--🔗 Mở trên GitHub                             ← href=<url>
--alice · +236/-48 5f · dev · ABC-997     ← disabled info line
Mới (20) … · Chờ author / đã comment … · Cũ > 30 ngày …
---
Review của chip
⏳ api#2069 newsletter…  đang chạy 3m
--👁 Xem chi tiết  --⏹ Dừng
🟡 shopbox-api#261 …  cần bạn
--👁 Xem chi tiết
✅ mailer-api#61 …  xong 11:40
--👁 Xem chi tiết  --🗑 Xoá
```

- The PR sections use the same groups and order as the inbox (re-review, new ≤ 30 days, waiting author / commented, older than 30 days). Empty sections are omitted.
- A PR that already has a run shows its run icon in front of its label, and its ▶ item reads "Chạy lại review".
- Titles are cut to 50 characters. Characters that SwiftBar treats specially (`|`, a leading `-`) are escaped.
- The icon is the GitHub mark as a base64 PNG `templateImage`, so macOS tints it for light and dark menu bars.
- If the fetch fails, the title becomes `!` next to the icon, the first menu line shows the error, and ↻ Refresh is still offered.

## Running a review (`chip run <label>`)

1. Look up the row by label in the cached inbox. If it is missing, refresh once, then look again. If it is still missing, notify the user and exit 1.
2. Resolve the local clone. If there is none, clone into `~/work/.chip-repos/<repo>` without asking, since clicking ▶ is the consent.
3. From that directory, run (values from the config):
   `claude --bg --name "chip · <label> · <skill>" --permission-mode <permission_mode> --disallowedTools <disallowed_tools…> "<skill prompt, filled>"`
4. Parse the session id that `--bg` prints, save `{id, url, repo, skill, started_at}` under `<label>|<skill name>` in `runs.json`, and notify "Đang review <label>".

## Run status

`claude agents --json --all` lists the sessions. A record matches by id, falling back to the name `chip · <label> · <skill name>`.

| Agent status | Shown as |
|---|---|
| `busy` | ⏳ đang chạy `<elapsed>` |
| `idle` | ✅ xong `<HH:MM>` |
| a status meaning the session waits for permission or input | 🟡 cần bạn |
| not listed (removed or crashed) | ⚪ không còn session; only 🗑 Xoá is offered |

The exact status strings are checked against `claude agents --json` output during implementation, and the mapping lives in one dict.

## Notifications

On each `chip swiftbar` run, the current state is diffed against `notify.json`, then the snapshot is written:

- **PR mới:** a label with status `new` that was not in the previous snapshot.
- **Cần re-review:** a label whose status became `re-review`.
- **Review xong:** a run that changed from `busy` to `idle`.
- **Review cần bạn:** a run that entered the waiting status.

The first run, when there is no snapshot yet, only writes the snapshot, so the user does not get 40 notifications. At most 3 notifications go out per refresh, plus a "+N PR khác" summary. Notifications use `osascript -e 'display notification … with title "chip"'`.

## Pluggable review skills (`~/.config/chip/config.json`)

Anyone can run their own skill instead of, or next to, `/my-review-skill`. The config file is optional, and the defaults reproduce today's behaviour:

```json
{
  "work_root": "~/work",
  "skills": [
    {"name": "Review đầy đủ", "prompt": "/my-review-skill {url}"}
  ],
  "permission_mode": "auto",
  "disallowed_tools": ["Edit", "Write", "NotebookEdit"]
}
```

- **`skills`:** each entry becomes one ▶ item in every PR's submenu, as `▶ <name>`. The first entry is the default. `prompt` is any text that Claude Code accepts as a first message, usually a slash command. It is filled from the placeholders `{url}`, `{repo}` (`owner/repo`), `{number}`, `{label}` and `{title}`. Unknown placeholders are an error that `chip config check` reports.
- **Running a skill:** `chip run <label> [--skill <index>]` runs the chosen entry, and the session name becomes `chip · <label> · <skill name>`. One label can then have several runs, one per skill, each listed under "Review của chip" with its skill name. `runs.json` is keyed by `<label>|<skill name>`.
- **`work_root`:** where `chip repo` scans for clones and where `.chip-repos/` lives. `CHIP_WORK_ROOT` still overrides it.
- **`permission_mode` / `disallowed_tools`:** passed to `claude --bg` as is. Users who want a skill that fixes code can drop `Edit`/`Write` from the list, at their own risk.
- **Bad JSON or a bad entry:** the menu shows one error line and falls back to the defaults, so it never goes blank.
- **`chip config init`:** writes the default file if it is missing. **`chip config check`:** validates the file and prints the resolved values.

The `/chip` skill and the fzf picker use the same config: their review step uses the default skill's prompt instead of the hard-coded `/my-review-skill`.

## Install (`chip menubar install`)

- `brew install swiftbar` (the user runs it, or the command prints it when SwiftBar is missing).
- Plugin folder: SwiftBar's configured `PluginDirectory`. If it is unset, use `~/Library/Application Support/SwiftBar/Plugins` and write that path with `defaults write com.ameba.SwiftBar PluginDirectory`.
- Symlink `chip.3m.sh` into the plugin folder, then `open -a SwiftBar`.

## Testing

Unit tests (stdlib `unittest`, no network, no real `claude` or `osascript`, all injected):
- menu rendering: sections, escaping, run markers, the error state, and the icon line;
- notification diff: the first run is silent, each of the four triggers, and the cap of 3;
- run status mapping from fixture `claude agents --json` output;
- `chip run`: the command line built, id parsing, the record written, and clone-on-missing;
- config: defaults, placeholder filling, unknown placeholders, bad JSON falling back to defaults, and one ▶ item per skill.

A manual check in SwiftBar on the real menu bar follows.
