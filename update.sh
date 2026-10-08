#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 0 ]; then
  echo "usage: ./update.sh"
  echo "fast-forwards this clone on main to origin/main, re-runs its install.sh and runs guild doctor"
  exit 2
fi

BASE="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" >/dev/null && pwd)"

if [ -n "$(git -C "$BASE" status --porcelain)" ]; then
  echo "update: $BASE has local changes; refusing to move it"
  exit 1
fi

if [ "$(git -C "$BASE" symbolic-ref --short -q HEAD)" != "main" ]; then
  echo "update: $BASE is not on main; refusing to move it"
  exit 1
fi

BEFORE="$(git -C "$BASE" rev-parse HEAD)"
git -C "$BASE" pull --quiet --ff-only origin main
AFTER="$(git -C "$BASE" rev-parse HEAD)"

if [ "$BEFORE" = "$AFTER" ]; then
  echo "update: already at $(git -C "$BASE" log --oneline -1)"
else
  echo "update: $(git -C "$BASE" rev-parse --short "$BEFORE") -> $(git -C "$BASE" rev-parse --short "$AFTER")"
  git -C "$BASE" log --first-parent --format='  %h %s' "$BEFORE..$AFTER"
fi

"$BASE/install.sh"

echo
echo "checks:"
if ! "$BASE/bin/guild" doctor; then
  echo "update: done, but the checks above need attention"
fi
