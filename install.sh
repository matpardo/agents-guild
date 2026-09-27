#!/usr/bin/env bash
set -euo pipefail

SOURCE="${BASH_SOURCE[0]}"
while [ -h "$SOURCE" ]; do
  DIR="$(cd -P "$(dirname "$SOURCE")" >/dev/null && pwd)"
  SOURCE="$(readlink "$SOURCE")"
  case "$SOURCE" in
    /*) ;;
    *) SOURCE="$DIR/$SOURCE" ;;
  esac
done
REPO_ROOT="$(cd -P "$(dirname "$SOURCE")" >/dev/null && pwd)"

TARGET_DIR="$HOME/.local/bin"
mkdir -p "$TARGET_DIR"
ln -sf "$REPO_ROOT/bin/guild" "$TARGET_DIR/guild"
echo "linked $TARGET_DIR/guild -> $REPO_ROOT/bin/guild"
echo "make sure $TARGET_DIR is on your PATH"
