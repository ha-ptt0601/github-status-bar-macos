# GitHubBar + chip — your PR review inbox for Claude Code

**GitHubBar** is a macOS menu bar app that shows the GitHub pull requests waiting for **your** review and your **own** open pull requests. With one click, it runs your Claude Code review skill on a PR in the background. **chip** is the command-line tool behind it. chip also powers a `/chip` skill, an `@`-mention picker inside Claude Code and an fzf picker in the terminal.

```
[GitHub 11 🔴1 🔵1]                      ← PRs to review · your PRs with changes requested · reviews running
[ Review requests · 30 | My pull requests · 75 · 🔴1 ]   ← tabs: switch without closing the menu
Updated 13:40
↻ Refresh now                           ← spinner "Refreshing…", then "✓ Up to date"
──────────────
[ 🔍 Search pull requests        ]      ← type to filter, right in the menu
▤ Projects ›
──────────────
API · 15 PRs
🟠 #2079  Re-review  ABC-997 feat(mcp): OAuth 2.1 agent au…  alice  ›
🟢 #2069  New        update(newsletter): migrate from retire…  alice  ›
10 more in API ›
MAILER-API · 2 PRs
🟢 #58    New        feat(campaigns): schedule a campaign …  bob  ›
Older than 30 days · 11 PRs ›
──────────────
Reviews by chip
🔵 shopbox-api#272 · Full review · running 3m ›
──────────────
Show approved & drafts (8) ›
Recent notifications ›
Settings ›
Open at Login ✓
Quit GitHubBar
```

## Features

### A menu that stays open
- **Tabs:** *Review requests* (default) and *My pull requests* sit in a tab bar at the top. Switching is instant and keeps the menu open; both tabs share one width, and the choice is remembered.
- **Refresh now** keeps the menu open: it shows a spinner and *Refreshing…* while it fetches from GitHub, updates the list in place, then says *✓ Up to date* for two seconds.
- **Projects ›** and **Settings › Status style** toggle their checkmarks without closing the menu, so you can hide several projects in a row.
- GitHubBar refreshes on its own every minute (GitHub data is cached for 3 minutes), so new PRs usually show up within a few minutes along with a notification.

### Review requests tab (default)
- **Every PR waiting for you**, from two searches: `review-requested:@me` and `reviewed-by:@me`. GitHub drops you from the requested reviewers once you review, so the second search is what keeps PRs that need a **re-review** visible.
- **Grouped by project.** Every project is always visible, with up to 5 PRs each and the rest under `N more in <project> ›`, paged 12 at a time with nested `Next ›` submenus.
- **Status on every row:** 🟠 Re-review (new commits after your review, or you were re-requested) · 🟢 New · ⚪ Waiting on author / Commented. PRs older than 30 days go under **Older than 30 days**, and approved PRs and drafts under **Show approved & drafts**.
- **PR submenu:**
  - the full title, status, author, age, size, base branch (flagged *stacked*), Jira key and conflict;
  - one `Run "<skill>"` button per configured review skill;
  - Open on GitHub and Copy link.

### My pull requests tab
- **Your open PRs, grouped by project.** Each row shows its status, first match wins: 🔴 Changes requested · ❌ CI failed · ⚠️ Conflict · 💬 N unresolved threads · ✅ Approved · ⚪ Waiting · ⚪ Draft.
- **Reviewer column:** `bob ✗ carol ✓` (✓ approved, ✗ changes requested, 💬 commented), or `→ bob, carol` while you are still waiting on requested reviewers.
- **Address review:** runs a skill that reads every unresolved thread, then **only proposes** the code change and drafts a reply for each one. It never edits files, commits, pushes or posts. `git commit`, `git push`, `gh pr comment` and `gh pr review` are blocked for these runs.
- **Re-request review** from the reviewers who have not approved yet.

### Background reviews, in rounds
- **Run** starts `claude "<your skill prompt>" --bg` inside the PR's local clone. chip finds the clone under `work_root`, or clones the repo into `work_root/.chip-repos/`. The run is read-only: permission mode `auto`, and `Edit`/`Write` are blocked.
- **The row follows the run:** 🔵 Reviewing → 🟡 Needs you (waiting for input or permission) → ✅ Reviewed. The icon shows `🔵N` and `🟡N` badges.
- **View session** opens the session in Terminal (`claude attach`), so you can read the report and keep talking to Claude.
- **Round resolved.** After you post your review on GitHub, or new commits land, the round is resolved: the PR goes back to its GitHub status and leaves "Reviews by chip". Merged or closed PRs resolve on their own.
- **Continue review (round N+1)** resumes **the same session**, so Claude still has round N in context. It checks whether each earlier finding was fixed, answered or is still open, then reviews only what changed.

### Search and filters
- **Search pull requests** is a field at the top of the menu, focused when the menu opens. Type and the tab shows only the PRs whose number, project, title, author, reviewers or Jira key contain all of your words, including PRs under *N more*, *Older than 30 days* and *Show approved & drafts* (up to 40 results). Clear the field to get the full list back. The text stays when you switch tabs.
- **Projects ›** hides or shows a project's PRs at once (✓ = shown). The choice is saved in your config.
- Outside GitHubBar (`chip swiftbar` without `--panes`, e.g. in SwiftBar), **Search…** opens a small dialog instead.

### Notifications (macOS)
You are notified about:
- new review requests and PRs that need a re-review;
- finished reviews and reviews waiting for you;
- reviews on your own PRs ("bob approved …", "… requested changes on …", "… commented on …");
- CI failures, conflicts, and new chip versions.

The first refresh after install is silent, and each refresh sends at most 3 notifications.

GitHubBar posts them as native macOS notifications (allow them when macOS asks). **Clicking one opens the PR**, or the review session for "Review finished" and "Review needs you". The last 10 are also kept under **Recent notifications ›** in the menu, with the same click actions and a **Clear** button.

### Other ways to pick PRs
- **Claude Code prompt bar:** type `/chip @`, pick PRs from the `@` autocomplete (served by chip's MCP server), and press Enter to review them one by one.
- **Chat menus:** `/chip menu`, or `/chip menu <words>` to search.
- **Terminal:** `chip` opens an fzf picker. Choose a project, tick PRs with Tab, and press Enter to review each PR in its repo.

### Updates
GitHubBar checks this repo's GitHub releases every 6 hours. When a newer version exists, the menu shows **Update available: vX — Update now**. Clicking it pulls the repo (fast-forward only), rebuilds and reinstalls.

## Install

**Prerequisites:**
- macOS 13 or later;
- Python 3.9 or later;
- Command Line Tools (`xcode-select --install`), which provide git and Swift;
- [GitHub CLI](https://cli.github.com) (`brew install gh`), logged in with `gh auth login` (see [Your GitHub account](#your-github-account));
- [Claude Code](https://claude.com/claude-code);
- optional: `brew install fzf` for the terminal picker.

### Your GitHub account

chip has no login of its own: every request goes through `gh` with **your** token, which `gh` keeps in the macOS Keychain. The searches use `@me` (`review-requested:@me`, `reviewed-by:@me`, `author:@me`), so each person sees their own PRs.

- Check which account is used: `gh auth status` (the line `Active account: true`).
- Several accounts: `gh auth login` adds another one; `gh auth switch` changes the active one. GitHubBar follows the active github.com account, at the next refresh or **Refresh now**. Note that this also switches the account for every other `gh` command on the machine.
- Organizations with SAML SSO: authorize the `gh` token for the organization (GitHub → Settings → Applications → GitHub CLI, or follow the link `gh` prints). Otherwise that organization's PRs do not appear.
- Only github.com is supported, not GitHub Enterprise Server.
- Updates come from this private repository's releases, so your account needs access to it.

### Get it

The repository is private. Ask for access, then:

```sh
git clone git@github.com:ha-ptt0601/chip.git ~/work/chip
~/work/chip/bin/chip install
```

`chip install` does the following:
1. links `~/.local/bin/chip`;
2. installs the `/chip` skill into `~/.claude/skills/chip`;
3. registers the `chip` MCP server for the `@` picker;
4. builds **GitHubBar.app** into `~/Applications`, signs it ad hoc, clears quarantine and launches it. The app adds itself to Login Items; toggle **Open at Login** in its menu;
5. removes the SwiftBar plugin that older chip versions used (SwiftBar is no longer needed);
6. writes a default `~/.config/chip/config.json`.

It is safe to run again, and it never overwrites files it did not create. `chip uninstall` removes exactly what it added; your config and cache are kept.

## Configuration

`chip install` writes `~/.config/chip/config.json` once; it is yours and is never overwritten. Open it with `chip config open` (or **Settings → Open config**), and check it with `chip config check`. GitHubBar picks up changes at the next refresh.

```json
{
  "work_root": "~/work",
  "skills": [
    {"name": "Full review", "prompt": "Review the pull request {url}. Use gh to read its description, diff … Do not edit files, commit, push, or post anything to GitHub."}
  ],
  "address_skills": [
    {"name": "Address review", "prompt": "Help me address the review feedback on my pull request {url}. …"}
  ],
  "permission_mode": "auto",
  "disallowed_tools": ["Edit", "Write", "NotebookEdit"],
  "terminal": "Terminal",
  "status_style": "dots",
  "hidden_projects": []
}
```

### Plug in your own review skill

The default **Full review** is a plain prompt that works on any machine. To use your own Claude Code skill, put it in `~/.claude/skills/<name>/SKILL.md` (or install it from a plugin), then point `skills` at it. You can have several; each becomes a `Run "<name>"` button on every PR:

```json
"skills": [
  {"name": "My review",    "prompt": "/my-review-skill {url}"},
  {"name": "Quick review", "prompt": "Review {url} briefly: only bugs and security issues."},
  {"name": "Full review",  "prompt": "Review the pull request {url}. …"}
]
```

- `prompt` is sent to `claude` as the first message, so it can call a skill (`/name …`) or be plain text.
- Placeholders are filled per PR: `{url}`, `{repo}`, `{number}`, `{label}`, `{title}`.
- The run is read-only (`disallowed_tools`), and "Continue review" rounds reuse the same prompt.
- `address_skills` works the same way for the **Address review** button on your own PRs.
- If the file is invalid, the menu shows an orange "Config: …" line and uses the defaults until you fix it.

### All keys

| Key | Meaning |
|---|---|
| `work_root` | Where chip looks for your local clones (up to 3 levels deep) and where `.chip-repos/` lives |
| `skills` | Review skills. Each one is a `Run "<name>"` button on every PR to review. Placeholders: `{url} {repo} {number} {label} {title}` |
| `address_skills` | Skills for your own PRs (the Address review button). Same placeholders |
| `permission_mode`, `disallowed_tools` | Passed to `claude --bg` for every run |
| `terminal` | `Terminal` or `iTerm`, used by View session |
| `status_style` | `dots` (🟠🟢⚪ + label), `emoji` (🔁 🆕 💬 ⏳ + legend) or `symbols` (SF Symbols). Also under **Settings → Status style** |
| `hidden_projects` | Projects hidden from the menu. Also under **Projects ›** |

## Command reference

| Command | What it does |
|---|---|
| `chip install` / `chip uninstall` / `chip update` | Set up, remove, or pull and reinstall |
| `chip` | fzf picker in the terminal |
| `chip list` | Markdown table of PRs to review |
| `chip run <label> [--skill N] [--address]` | Start a background review (or an Address review on your PR) |
| `chip attach / stop / forget <session-id>` | Open, stop or remove a chip review session |
| `chip nudge <label>` | Re-request review on your PR |
| `chip view review\|mine` | Switch the menu tab |
| `chip notifications --clear` | Empty the Recent notifications menu |
| `chip search [--clear]` · `chip project toggle <name>\|all` | Search and project filter |
| `chip config init\|check\|path\|open\|set <key> <value>` | Configuration |
| `chip swiftbar [--view review\|mine] [--panes] [--deliver]` | Print the menu. GitHubBar uses `--panes` (both tabs, in-menu search) and `--deliver` (queued notifications) |
| `chip mcp` | MCP server used by Claude Code's `@` picker |

## Development

- Python tests: `python3 -m unittest discover -s tests -t .` (stdlib only).
- GitHubBar (`app/`, Swift, AppKit): `swift build -c release --package-path app`. Parser checks: `swift run --package-path app GitHubBarChecks [menu.txt]`. Command Line Tools ship no XCTest, so the checks are a plain executable.
- After editing `skill/SKILL.md` or the app, run `chip install` to re-render the skill and rebuild the app.
- Release from `main`: `scripts/release.sh X.Y.Z`. It bumps the version, runs the tests, tags and creates a GitHub release.
