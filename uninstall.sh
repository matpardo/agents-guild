#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -gt 1 ] || { [ "$#" -eq 1 ] && [ "$1" != "--purge" ]; }; then
  echo "usage: ./uninstall.sh [--purge]"
  echo "removes the timers, the hooks and permission rules, and the symlinks install.sh made; --purge also deletes the data, config and state directories"
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

SYSTEMD_USER_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
HAS_SYSTEMCTL=0
if command -v systemctl >/dev/null 2>&1; then
  HAS_SYSTEMCTL=1
fi
REMOVED_UNITS=0
for name in guild-sync-gh guild-sync-sdd guild-sync-tracker guild-sync-bases guild-resources-collect guild-compact guild-dispatch; do
  if [ ! -e "$SYSTEMD_USER_DIR/$name.timer" ] && [ ! -e "$SYSTEMD_USER_DIR/$name.service" ]; then
    continue
  fi
  if [ "$HAS_SYSTEMCTL" -eq 1 ]; then
    systemctl --user disable --now "$name.timer" || true
  fi
  rm -f "$SYSTEMD_USER_DIR/$name.timer" "$SYSTEMD_USER_DIR/$name.service"
  echo "removed $name from $SYSTEMD_USER_DIR"
  REMOVED_UNITS=1
done
if [ "$REMOVED_UNITS" -eq 1 ] && [ "$HAS_SYSTEMCTL" -eq 1 ]; then
  systemctl --user daemon-reload || true
fi
if [ "$REMOVED_UNITS" -eq 1 ] && [ "$HAS_SYSTEMCTL" -eq 0 ]; then
  echo "systemctl not found; removed the unit files without disabling the timers"
fi

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
