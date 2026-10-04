# chip — PR review inbox for Claude Code

chip lists the GitHub pull requests waiting for **your** review and runs your review skill on the ones you pick.

- **Menu bar** (SwiftBar): GitHub icon with a count, PRs grouped by project, a `Run "<skill>"` button per PR, live status of background reviews (View / Stop / Remove), and notifications for new PRs, re-reviews, finished reviews and new chip versions.
- **Two tabs in one menu**: *Review requests* (default) lists PRs waiting for your review; *My pull requests* lists your own PRs (status, reviewers, unresolved threads, an "Address review" skill that only drafts fixes and replies, and Re-request review). Both have **Search…** and a **Projects** filter.
- **Prompt bar**: type `/chip @` in Claude Code and pick PRs from the `@` autocomplete.
- **In chat**: `/chip menu` (pick from menus). **In a shell**: `chip` (fzf picker, Tab to tick).

## Install

Prerequisites: macOS, Python 3.9+, [`gh`](https://cli.github.com) (logged in), [Claude Code](https://claude.com/claude-code). Optional: `brew install swiftbar fzf`.

```sh
git clone git@github.com:ha-ptt0601/chip.git ~/work/chip
~/work/chip/bin/chip install
```

`chip install` links `~/.local/bin/chip`, installs the `/chip` skill, registers the `chip` MCP server, adds the SwiftBar plugin and writes a default config. Running it again is safe. `chip uninstall` removes exactly what it added.

## Plug in your own review skill

Edit `~/.config/chip/config.json` (`chip config open`), then check it with `chip config check`:

```json
{
  "work_root": "~/work",
  "skills": [
    {"name": "Full review", "prompt": "/my-review-skill {url}"},
    {"name": "Quick review", "prompt": "/code-review {url}"}
  ],
  "permission_mode": "auto",
  "disallowed_tools": ["Edit", "Write", "NotebookEdit"],
  "terminal": "Terminal",
  "status_style": "dots"
}
```

`status_style` picks how PR status is shown in the menu: `dots` (🟠 Re-review · 🟢 New · ⚪ Commented/Waiting, with the label), `emoji` (🔁 🆕 💬 ⏳ with a legend) or `symbols` (SF Symbols). Switch it from the menu under **Settings → Status style**, or with `chip config set status_style emoji`.

Each skill becomes a `Run "<name>"` button on every PR. Placeholders: `{url} {repo} {number} {label} {title}`. Reviews run in a background Claude Code session (`claude --bg`) inside the PR's local clone (found under `work_root`, or cloned into `work_root/.chip-repos/`).

## Review rounds

Each Run is a **round** in a background Claude Code session. While it runs the PR row shows 🔵 Reviewing; when it finishes, ✅ Reviewed, and it is listed under **Reviews by chip**. Open the session, then act on GitHub (post your review) or push fixes. As soon as GitHub shows your review or newer commits after the round started, the round is **resolved**: the row goes back to its GitHub status and the PR leaves "Reviews by chip". The PR still remembers the session: its submenu shows `Last chip review · round N` with **Continue review (round N+1)**, which continues the same session and checks whether the previous findings were addressed, and **Open last session**.

## Updating

The menu shows **Update available** when a newer release exists. Click it, or run `chip update`. Maintainers release with `scripts/release.sh X.Y.Z` from `main`.

## Development

`python3 -m unittest discover -s tests -t .` (stdlib only). After editing `skill/SKILL.md`, run `chip install` to re-render the installed skill.
