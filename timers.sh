#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 0 ]; then
  echo "usage: ./timers.sh"
  echo "installs or refreshes the guild systemd user timers, keeping the interval of the ones already installed"
  exit 2
fi

if ! command -v systemctl >/dev/null 2>&1; then
  echo "timers: systemctl not found; skipping (guild <name>-timer print shows the units)"
  exit 0
fi

UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"

installed_interval() {
  local timer_file="$UNIT_DIR/$1"
  local seconds
  seconds="$(sed -n 's/^OnUnitActiveSec=\([0-9]*\)s$/\1/p' "$timer_file" 2>/dev/null || true)"
  [ -n "$seconds" ] || return 0
  if [ $((seconds % 86400)) -eq 0 ]; then
    echo "$((seconds / 86400))d"
  elif [ $((seconds % 3600)) -eq 0 ]; then
    echo "$((seconds / 3600))h"
  else
    echo "$((seconds / 60))m"
  fi
}

install_timer() {
  local command_name="$1"
  local timer_name="$2"
  local default_every="$3"
  local every
  every="$(installed_interval "$timer_name")"
  guild "$command_name" install --every "${every:-$default_every}"
}

install_timer sync-timer guild-sync-gh.timer 10m
install_timer sync-sdd-timer guild-sync-sdd.timer 10m
install_timer sync-tracker-timer guild-sync-tracker.timer 10m
install_timer sync-bases-timer guild-sync-bases.timer 1m
install_timer resources-timer guild-resources-collect.timer 2h
install_timer compact-timer guild-compact.timer 1d
