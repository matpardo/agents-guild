---
epic: install-and-update
type: tasks
title: Versioned install and self-update
status: active
updated: 2026-10-17
---

# Tasks: Versioned install and self-update

## T01 — Update script and doctor

**Depends on:** —
**Status:** [x] done — #15

**What:** `./update.sh <installed-worktree>` refuses local changes, moves the installed checkout to `origin/main`, lists the commits it brought, re-runs `install.sh` and runs `guild doctor`. `guild doctor` reports missing hooks in `~/.claude/settings.json`, a missing `~/.claude/GUILD.md` and invalid project configs, without writing anything.

## T02 — Tagged releases and guild version

**Depends on:** T01
**Status:** [x] done — #188

**What:** `v0.x.y` tags with a CHANGELOG; `guild version` shows the installed version and whether a newer release exists.

## T03 — Install script into a managed location

**Depends on:** T02
**Status:** [x] done — #188

**What:** an install script that places guild in `~/.local/share/guild/app` pinned to the latest release tag; running it again updates.

## T04 — guild self-update and new-release hint

**Depends on:** T03
**Status:** [x] done — #188

**What:** `guild self-update [--to <tag>]`, and the session-start brief mentions a newer release (checked in the background).

## T05 — The installed guild ignores the working directory

**Depends on:** T01
**Status:** [x] done — #26

**What:** `python3 -m guild` put the current directory ahead of `PYTHONPATH`, so running `guild` from inside any guild checkout (the development one included) ran that checkout's code instead of the installed one — the hole behind the earlier "edits go live" incident. `bin/guild` and the background sync spawned by `session-start` now start Python in isolated mode (`-I`) and put their own repo first explicitly.

## T06 — The CLAUDE.md hint prints only when the line is missing

**Depends on:** T01
**Status:** [x] done — #172

**What:** `install.sh`, and so every `./update.sh`, printed the hint to add `@~/.claude/GUILD.md` to `~/.claude/CLAUDE.md` even when the line was already there. It now prints only when `grep` does not find the line, following a symlinked `CLAUDE.md`.

## T07 — Doctor reports the timers and `timers.sh` keeps them current

**Depends on:** T01
**Status:** [x] done — #188

**What:** `install.sh` and `update.sh` never installed the systemd timers, so a fresh machine ran without them. `guild doctor` now warns per timer that is missing or drifted from its template (a moved `guild` path, an edited unit), keeping an installed interval as valid; `./update.sh` runs doctor, so the warning shows after each update. The new `./timers.sh` installs or refreshes the five timers (sync gh/sdd/tracker 10m, resources 2h, compact 1d), keeping the interval of any timer already installed. Nothing installs them unasked.
