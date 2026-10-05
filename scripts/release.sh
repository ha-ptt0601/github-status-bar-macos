#!/bin/bash
# Usage: scripts/release.sh X.Y.Z — bump, test, build GitHubBar.dmg, tag and publish a GitHub release.
# The release notes are CHANGELOG.md's "## vX.Y.Z" section, then the install steps.
set -euo pipefail
v="${1:?usage: scripts/release.sh X.Y.Z}"
[[ "$v" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "version must be X.Y.Z"; exit 1; }
cd "$(dirname "$0")/.."
[ -z "$(git status --porcelain)" ] || { echo "working tree not clean"; exit 1; }
[ "$(git branch --show-current)" = main ] || { echo "release from main"; exit 1; }
changes="$(scripts/release-notes.sh "$v")"
[ -n "$changes" ] || { echo "write the \"## v$v\" section in CHANGELOG.md first"; exit 1; }
prev="$(git describe --tags --abbrev=0)"
sed -i '' "s/^__version__ = .*/__version__ = \"$v\"/" chip/__init__.py
python3 -m unittest discover -s tests -t . -q
python3 -c 'import sys; from chip import installer; sys.exit(installer.package() is None)'  # dist/GitHubBar.dmg
git diff --quiet || git commit -qam "release: v$v"  # nothing to commit when the version is already $v
git tag "v$v"
git push -q origin main "v$v"
notes="$changes

## Install

Download **\`GitHubBar.dmg\`** below, open it and drag **GitHubBar.app** to **Applications**. The app is signed ad hoc, not notarized, so the first time macOS cannot verify the developer: open **System Settings › Privacy & Security** and click **Open Anyway**, or clear the download flag once:

\`\`\`sh
xattr -dr com.apple.quarantine /Applications/GitHubBar.app
\`\`\`

Already installed? Use **Update now** in the menu. Full walkthrough in the [README](https://github.com/ha-ptt0601/github-status-bar-macos#install).

**Full changelog:** [$prev...v$v](https://github.com/ha-ptt0601/github-status-bar-macos/compare/$prev...v$v)
"
gh release create "v$v" --title "v$v" --notes "$notes" dist/GitHubBar.dmg
echo "released v$v"
