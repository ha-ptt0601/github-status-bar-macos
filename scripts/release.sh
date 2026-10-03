#!/bin/bash
# Usage: scripts/release.sh X.Y.Z — bump, test, tag and publish a GitHub release.
set -euo pipefail
v="${1:?usage: scripts/release.sh X.Y.Z}"
[[ "$v" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "version must be X.Y.Z"; exit 1; }
cd "$(dirname "$0")/.."
[ -z "$(git status --porcelain)" ] || { echo "working tree not clean"; exit 1; }
[ "$(git branch --show-current)" = main ] || { echo "release from main"; exit 1; }
sed -i '' "s/^__version__ = .*/__version__ = \"$v\"/" chip/__init__.py
python3 -m unittest discover -s tests -t . -q
git commit -qam "release: v$v"
git tag "v$v"
git push -q origin main "v$v"
gh release create "v$v" --title "chip v$v" --generate-notes
echo "released v$v"
