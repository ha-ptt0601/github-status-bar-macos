# Changelog

Each section is a release's notes on GitHub: `scripts/release.sh X.Y.Z` publishes the `## vX.Y.Z` section, followed by the install steps.

## v0.1.17

### Changed
- **"Open feature session" finds the session that opened the PR.** When Claude Code creates a PR (`gh pr create`), it records the link in that session. GitHubBar now picks that session as the PR's feature session, before the busiest session on the PR's branch, so a branch worked on in several sessions no longer opens the wrong one. A session you linked by hand still wins.

## v0.1.16

### Fixed
- **A PR waiting on its author shows that status again.** A review round started after you had already reviewed the same commits (for example "Continue review" with no new push) stayed in "Reviews by GitHubBar" and its dot replaced the PR's status. Once such a round finishes, it resolves as "waiting for the author".

## v0.1.15

### Fixed
- **A review you followed up on shows when it really finished.** If you opened a review's session and asked something before GitHubBar noticed the review had finished, the review stayed "running" during your follow-up and then showed the follow-up's end as its time. GitHubBar now reads the session: a message you typed after the review prompt means the review had finished, at the end of its last turn before your message.

## v0.1.14

### Changed
- **"Update available — Update now" sits at the bottom of the menu**, next to Open at Login and Quit, instead of above the tabs.

## v0.1.13

GitHubBar.dmg now opens like a normal Mac installer, and every release says what changed.

### Changed
- **A tidy .dmg window.** Opening `GitHubBar.dmg` shows big icons: GitHubBar on the left, Applications on the right. Drag one onto the other.
- **Release notes.** Each release lists what changed and how to install it.

## v0.1.12

GitHubBar is now a normal Mac app: download the .dmg, drag it to Applications, open it. No clone, no Swift build.

### Added
- **`GitHubBar.dmg` on every release.** The app runs on Apple silicon and Intel Macs (macOS 13+) and carries chip inside it.
- **Set-up on first launch.** GitHubBar links `~/.local/bin/chip`, installs the `/chip` skill, registers the `chip` MCP server and writes a default config, and does it again after each update.
- **Update now replaces the app.** It downloads the new release's `GitHubBar.dmg`, swaps the app and opens it again.
- GitHubBar finds `gh`, `git` and `claude` through your login shell's `PATH`, as in Terminal.

### Changed
- Installing from a clone (`bin/chip install`) is now the way for contributors.
- `chip install` no longer looks for SwiftBar plugins from early chip versions.

## v0.1.11

### Fixed
- **A finished review stays finished.** Opening a review's session ("Open last session") and asking it something no longer turns the review back into "running" and then posts a second "Review finished" with a new time.
