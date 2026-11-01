---
epic: solo-players
type: tasks
title: Built-in per-repo solo players
status: active
updated: 2026-11-01
---

# Tasks: Built-in per-repo solo players

## T01 — Config and triggers

**Depends on:** —
**Status:** [x] done

**What:** `solo_players` in the project config, the built-in jobs with their prompts, the derived health jobs, the red main trigger and the `dependabot_status` sync with the `dependabot.synced` event.

**Acceptance:**
- [x] Each invalid shape fails to load with a message naming the key.
- [x] A billing-blocked main never triggers and Dependabot facts record only when they change.

## T02 — Board and web section

**Depends on:** T01
**Status:** [x] done

**What:** a `SOLO PLAYERS` section in `guild board` and the web, with the launch command for a due or idle player.

**Acceptance:**
- [x] The CLI and the web show name, class, repo, trigger, state, last report and last pending text.

## T03 — Manual launch

**Depends on:** T01
**Status:** [x] done

**What:** `guild solo list` and `guild solo launch <owner/repo> <job>`, sharing the tmux launch of `guild adventurer launch`.

**Acceptance:**
- [x] Launch opens a `solo-` window even when the player is not due and refuses inside a session.
