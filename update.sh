#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "usage: ./update.sh <installed-worktree>"
  echo "moves the installed checkout to origin/main, re-runs its install.sh and runs guild doctor"
  exit 2
fi

if ! LIVE="$(cd "$1" 2>/dev/null && pwd)" || ! git -C "$LIVE" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "update: $1 is not a git checkout"
  exit 1
fi

if [ -n "$(git -C "$LIVE" status --porcelain)" ]; then
  echo "update: $LIVE has local changes; refusing to move it"
  exit 1
fi

BEFORE="$(git -C "$LIVE" rev-parse HEAD)"
git -C "$LIVE" fetch --quiet origin
git -C "$LIVE" checkout --quiet --detach origin/main
AFTER="$(git -C "$LIVE" rev-parse HEAD)"

if [ "$BEFORE" = "$AFTER" ]; then
  echo "update: already at $(git -C "$LIVE" log --oneline -1)"
else
  echo "update: $(git -C "$LIVE" rev-parse --short "$BEFORE") -> $(git -C "$LIVE" rev-parse --short "$AFTER")"
  git -C "$LIVE" log --first-parent --format='  %h %s' "$BEFORE..$AFTER"
fi

"$LIVE/install.sh"

echo
echo "checks:"
if ! "$LIVE/bin/guild" doctor; then
  echo "update: done, but the checks above need attention"
fi
