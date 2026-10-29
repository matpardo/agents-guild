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

link_or_warn() {
  local source="$1"
  local target="$2"
  if [ -e "$target" ] || [ -L "$target" ]; then
    if [ -L "$target" ] && [ "$(readlink "$target")" = "$source" ]; then
      ln -sfn "$source" "$target"
      echo "linked $target -> $source"
      return 0
    fi
    echo "WARN: $target exists and is not a symlink to $source; leaving it untouched"
    return 0
  fi
  ln -sfn "$source" "$target"
  echo "linked $target -> $source"
}

TARGET_DIR="$HOME/.local/bin"
mkdir -p "$TARGET_DIR"
link_or_warn "$REPO_ROOT/bin/guild" "$TARGET_DIR/guild"
echo "make sure $TARGET_DIR is on your PATH"

CLAUDE_DIR="$HOME/.claude"
mkdir -p "$CLAUDE_DIR"
link_or_warn "$REPO_ROOT/GUILD.md" "$CLAUDE_DIR/GUILD.md"
"$REPO_ROOT/bin/guild" wire-settings
if ! grep -qsF '@~/.claude/GUILD.md' "$CLAUDE_DIR/CLAUDE.md"; then
  echo "add the line @~/.claude/GUILD.md to $CLAUDE_DIR/CLAUDE.md so every session loads the agent rules"
fi
