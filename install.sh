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

CLAUDE_DIR="$HOME/.claude"
mkdir -p "$CLAUDE_DIR"
ln -sfn "$REPO_ROOT/GUILD.md" "$CLAUDE_DIR/GUILD.md"
echo "linked $CLAUDE_DIR/GUILD.md -> $REPO_ROOT/GUILD.md"
echo "add the line @~/.claude/GUILD.md to $CLAUDE_DIR/CLAUDE.md so every session loads the agent rules"
