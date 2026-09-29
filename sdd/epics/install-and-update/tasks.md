---
epic: install-and-update
type: tasks
title: Versioned install and self-update
status: active
updated: 2026-09-29
---

# Tasks: Versioned install and self-update

## T01 — Update script and doctor

**Depends on:** —
**Status:** [x] done — #15

**What:** `./update.sh <installed-worktree>` refuses local changes, moves the installed checkout to `origin/main`, lists the commits it brought, re-runs `install.sh` and runs `guild doctor`. `guild doctor` reports missing hooks in `~/.claude/settings.json`, a missing `~/.claude/GUILD.md` and invalid project configs, without writing anything.

## T02 — Tagged releases and guild version

**Depends on:** T01
**Status:** [ ] pending

**What:** `v0.x.y` tags with a CHANGELOG; `guild version` shows the installed version and whether a newer release exists.

## T03 — Install script into a managed location

**Depends on:** T02
**Status:** [ ] pending

**What:** an install script that places guild in `~/.local/share/guild/app` pinned to the latest release tag; running it again updates.

## T04 — guild self-update and new-release hint

**Depends on:** T03
**Status:** [ ] pending

**What:** `guild self-update [--to <tag>]`, and the session-start brief mentions a newer release (checked in the background).

## T05 — The installed guild ignores the working directory

**Depends on:** T01
**Status:** [x] done — #26

**What:** `python3 -m guild` put the current directory ahead of `PYTHONPATH`, so running `guild` from inside any guild checkout (the development one included) ran that checkout's code instead of the installed one — the hole behind the earlier "edits go live" incident. `bin/guild` and the background sync spawned by `session-start` now start Python in isolated mode (`-I`) and put their own repo first explicitly.
