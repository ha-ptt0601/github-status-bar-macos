# Changelog

Each section is a release's notes on GitHub: `scripts/release.sh X.Y.Z` publishes the `## vX.Y.Z` section, followed by the install steps.

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
