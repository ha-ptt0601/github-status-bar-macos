#!/bin/bash
# Usage: scripts/release-notes.sh X.Y.Z — print CHANGELOG.md's "## vX.Y.Z" section (without its heading).
set -euo pipefail
cd "$(dirname "$0")/.."
awk -v head="## v$1" '$0 == head {on = 1; next} on && /^## / {exit} on' CHANGELOG.md \
  | sed -e '/./,$!d' | sed -e :a -e '/^\n*$/{$d;N;ba' -e '}'
