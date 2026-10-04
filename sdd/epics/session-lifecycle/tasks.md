---
epic: session-lifecycle
type: tasks
title: Handoffs that clean up and sessions that respawn
status: done
updated: 2026-10-04
---

# Tasks: Handoffs that clean up and sessions that respawn

## T01 — Consumed handoffs and retention config

**Depends on:** —
**Status:** [x] done — #73

**What:** `leaders.handoff_consumed_at` set by the `party.resumed` reducer on the previous generation, a local `handoff.pruned` event that clears `leaders.handoff_path`, and `handoff_retention_days` project config validation.

**Acceptance:**
- [x] Resuming generation N+1, by the hook or by `party resume`, marks generation N consumed.
- [x] `rebuild` reproduces the consumed mark and the cleared path.
- [x] Invalid retention values are rejected and absence is valid.

## T02 — Handoff file pruning

**Depends on:** T01
**Status:** [x] done — #73

**What:** `guild/handoff_prune.py` decides which handoff files go: superseded and consumed, or a closed party's last one past `handoff_retention_days`; symlinks and paths outside the handoffs directory are skipped.

**Acceptance:**
- [x] The latest handoff of an open party is never deleted and a superseded unconsumed one is kept.
- [x] A closed party's last handoff is kept without retention config and deleted once the retention has passed.
- [x] Symlinks and outside paths are skipped and reported.
- [x] A second run deletes and records nothing.

## T03 — State marker pruning, CLI, sync and party close

**Depends on:** T02
**Status:** [x] done — #73

**What:** Markers under `ctx/` and `hints/` of dead sessions are pruned too; `guild handoff prune [--dry-run]` reports it, `sync --source gh` and `party close` run it.

**Acceptance:**
- [x] Markers of running sessions or open-party leaders are kept, as are `human` and unknown names.
- [x] Without a session registry nothing is deleted.
- [x] `--dry-run` lists the same actions and deletes nothing.
- [x] A prune failure during sync is reported in the failures and does not abort it.
- [x] `party close` reports the pruned count only when it is above zero.

## T04 — Keeper parties

**Depends on:** —
**Status:** [x] done — #73

**What:** `parties.keeper`, `party start --keeper`, a Remote Control flag in the resume and fresh commands, keeper-aware `revive` and a keeper context nudge.

**Acceptance:**
- [x] The flag persists across generations and rebuild, and a legacy start event replays as non-keeper.
- [x] Revive commands for a keeper include `--remote-control <party>-g<N>` in both forms and non-keepers are unchanged.
- [x] The keeper nudge names `guild handoff --respawn` and the normal nudge is unchanged.

## T05 — Shared tmux launcher and window records

**Depends on:** T04
**Status:** [x] done — #73

**What:** `guild/tmux_windows.py` holds the tmux helpers extracted from `revive`; `leader.window_launched` events project to `leader_windows`, recorded by `revive` and cleaned on resume and close.

**Acceptance:**
- [x] `revive` behaves as before apart from recording the window.
- [x] The window is recorded under the generation the session will hold.
- [x] Older generations' records are removed on resume and all of them on close.

## T06 — Handoff respawn

**Depends on:** T04, T05
**Status:** [x] done — #73

**What:** `guild handoff --respawn` launches the next generation, waits for it to bind and closes its own window only when guild recorded it.

**Acceptance:**
- [x] A keeper respawns with Remote Control and the old window is closed after the bind.
- [x] A launch failure or a bind timeout keeps the old session, prints the manual command and kills nothing.
- [x] An unrecorded window, a mismatched pane or running outside tmux prints a manual close line and kills nothing.

## T07 — Docs and spec

**Depends on:** T03, T06
**Status:** [x] done — #73

**What:** README and `GUILD.md` describe handoff, prune, keepers and respawn; the spec is active.

**Acceptance:**
- [x] `test_sdd_docs` passes.
- [x] The README commands match the CLI.
