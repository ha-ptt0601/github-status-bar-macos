# GitHubBar + chip — your PR review inbox for Claude Code

**GitHubBar** is a macOS menu bar app that shows the GitHub pull requests waiting for **your** review and your **own** open pull requests. With one click, it runs your Claude Code review skill on a PR in the background. **chip** is the command-line tool behind it. chip also powers a `/chip` skill, an `@`-mention picker inside Claude Code and an fzf picker in the terminal.

```
[GitHub 11 🔴1 🔵1]                      ← PRs to review · your PRs with changes requested · reviews running
✓ Review requests · 30                  ← tab (default)
  My pull requests · 75 · 🔴1           ← tab
Updated 13:40
↻ Refresh now
──────────────
🔍 Search…
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
Settings ›
Open at Login ✓
Quit GitHubBar
```

## Features

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
- **Search…** opens a small dialog. Both tabs then show only the PRs whose label, repo, title, author, reviewers and Jira key contain all of your words, with a `"query" · N matches — Clear search` line on top.
- **Projects ›** lets you hide or show projects (✓ = shown). The choice is saved in your config.

### Notifications (macOS)
You are notified about:
- new review requests and PRs that need a re-review;
- finished reviews and reviews waiting for you;
- reviews on your own PRs ("bob approved …", "… requested changes on …", "… commented on …");
- CI failures, conflicts, and new chip versions.

The first refresh after install is silent, and each refresh sends at most 3 notifications.

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
- [GitHub CLI](https://cli.github.com), logged in with `gh auth login`;
- [Claude Code](https://claude.com/claude-code);
- optional: `brew install fzf` for the terminal picker.

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

Open the config with `chip config open` (or **Settings → Open config**), and check it with `chip config check`:

```json
{
  "work_root": "~/work",
  "skills": [
    {"name": "Full review", "prompt": "/my-review-skill {url}"},
    {"name": "Quick review", "prompt": "/code-review {url}"}
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
| `chip search [--clear]` · `chip project toggle <name>\|all` | Search and project filter |
| `chip config init\|check\|path\|open\|set <key> <value>` | Configuration |
| `chip swiftbar [--view review\|mine]` | Print the menu (what GitHubBar renders) |
| `chip mcp` | MCP server used by Claude Code's `@` picker |

## Development

- Python tests: `python3 -m unittest discover -s tests -t .` (stdlib only).
- GitHubBar (`app/`, Swift, AppKit): `swift build -c release --package-path app`. Parser checks: `swift run --package-path app GitHubBarChecks [menu.txt]`. Command Line Tools ship no XCTest, so the checks are a plain executable.
- After editing `skill/SKILL.md` or the app, run `chip install` to re-render the skill and rebuild the app.
- Release from `main`: `scripts/release.sh X.Y.Z`. It bumps the version, runs the tests, tags and creates a GitHub release.
