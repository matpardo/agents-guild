#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -gt 1 ] || { [ "$#" -eq 1 ] && [ "$1" != "--purge" ]; }; then
  echo "usage: ./uninstall.sh [--purge]"
  echo "removes the hooks and permission rules, and the symlinks install.sh made; --purge also deletes the data, config and state directories"
  exit 2
fi
PURGE="${1:-}"

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

unlink_or_warn() {
  local source="$1"
  local target="$2"
  if [ -L "$target" ] && [ "$(readlink "$target")" = "$source" ]; then
    rm -f "$target"
    echo "removed $target"
    return 0
  fi
  if [ -e "$target" ] || [ -L "$target" ]; then
    echo "WARN: $target is not a symlink to $source; leaving it untouched"
  fi
}

"$REPO_ROOT/bin/guild" unwire-settings

unlink_or_warn "$REPO_ROOT/bin/guild" "$HOME/.local/bin/guild"
unlink_or_warn "$REPO_ROOT/GUILD.md" "$HOME/.claude/GUILD.md"

for dir in "${XDG_DATA_HOME:-$HOME/.local/share}/guild" "${XDG_CONFIG_HOME:-$HOME/.config}/guild" "${XDG_STATE_HOME:-$HOME/.local/state}/guild"; do
  if [ ! -e "$dir" ]; then
    continue
  fi
  if [ "$PURGE" = "--purge" ]; then
    rm -rf "$dir"
    echo "deleted $dir"
    continue
  fi
  echo "kept data: $dir (rerun with --purge to delete it)"
done

if grep -qsF '@~/.claude/GUILD.md' "$HOME/.claude/CLAUDE.md"; then
  echo "remove the line @~/.claude/GUILD.md from $HOME/.claude/CLAUDE.md by hand"
fi
HUSKY_INIT="$HOME/.config/husky/init.sh"
if grep -qsF 'guild hook pre-commit' "$HUSKY_INIT"; then
  grep -nF 'guild hook pre-commit' "$HUSKY_INIT"
fi
echo "remove by hand any guild hook pre-commit line in $HUSKY_INIT or in a repository's .git/hooks/pre-commit"
