# chip — PR review inbox for Claude Code

chip lists the GitHub pull requests waiting for **your** review and runs your review skill on the ones you pick.

- **Menu bar** (SwiftBar): GitHub icon with a count, PRs grouped by project, a `Run "<skill>"` button per PR, live status of background reviews (View / Stop / Remove), and notifications for new PRs, re-reviews, finished reviews and new chip versions.
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
  "terminal": "Terminal"
}
```

Each skill becomes a `Run "<name>"` button on every PR. Placeholders: `{url} {repo} {number} {label} {title}`. Reviews run in a background Claude Code session (`claude --bg`) inside the PR's local clone (found under `work_root`, or cloned into `work_root/.chip-repos/`).

## Updating

The menu shows **Update available** when a newer release exists. Click it, or run `chip update`. Maintainers release with `scripts/release.sh X.Y.Z` from `main`.

## Development

`python3 -m unittest discover -s tests -t .` (stdlib only). After editing `skill/SKILL.md`, run `chip install` to re-render the installed skill.
