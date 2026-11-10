---
epic: session-lifecycle
type: tasks
title: Handoffs that clean up and sessions that respawn
status: done
updated: 2026-10-18
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

## T08 — Tmux copies reach the system clipboard

**Depends on:** T05
**Status:** [x] done — #109

**What:** The `guild` tmux session sets `copy-command` to `wl-copy`, `xclip` or `xsel` when present, and `guild doctor` warns when none is found.

**Acceptance:**
- [x] `wl-copy` is preferred on Wayland; X11 tools are used only with `DISPLAY` set.
- [x] With no tool found only OSC 52 remains and no `copy-command` is set.
- [x] `guild doctor` warns, without failing, when tmux is installed and no clipboard tool is found.

## T09 — Remove keeper parties

**Depends on:** T06
**Status:** [x] done — #160

**What:** `party start --keeper`, the `--remote-control` launch flag and `handoff --respawn` are removed; the `parties.keeper` column is dropped and old events still replay.

**Acceptance:**
- [x] No command or flag mentions keeper or respawn.
- [x] Rebuilding a log with `keeper: true` events succeeds and the column is gone.

## T10 — Respawn the next generation at the context limit

**Depends on:** T09
**Status:** [x] done — #169

**What:** a compaction nudges the session toward a handoff whatever the percentage, and `handoff --respawn` is back for sessions in a recorded window: it launches and binds the next generation itself and closes the old pane. Decision `20261016_respawn-on-context-limit`.

**Acceptance:**
- [x] SessionStart with `source: compact` resets the nudge marker and nudges a bound session.
- [x] The nudge asks for `--respawn` only when the current generation has a recorded window.
- [x] `--respawn` without a recorded window, or with `--close`, is refused before anything is written.

## T11 — Doctor warns when the handoff threshold sits above compaction

**Depends on:** T10
**Status:** [x] done — #170

**What:** the compact `SessionStart` records the last context percentage per project, and `guild doctor` warns when a project's `handoff_threshold` is at or above the lowest one, because that percentage nudge never fires.

**Acceptance:**
- [x] SessionStart with `source: compact` appends the pre-compact percentage for the bound project.
- [x] `guild doctor` warns, without changing the exit code, when `handoff_threshold` is at or above the lowest recorded value.
- [x] No samples, or a threshold below them, prints nothing.

## T12 — Handoff threshold follows the last automatic compaction

**Depends on:** T11
**Status:** [x] done — #171

**What:** a `PreCompact` hook (matcher `auto`) records the pre-compact context percentage globally, and a global `handoff_margin` in `guild.json` makes every project's threshold the last compaction minus the margin. Board, web and doctor show the value and its source. Decisión del dev, 2026-10-17: the margin is global because the compaction point comes from the user's Claude Code settings.

**Acceptance:**
- [x] `PreCompact` with trigger `auto` appends the session's last percentage; manual `/compact` and the compact `SessionStart` record nothing.
- [x] With `handoff_margin` and a sample, the threshold is the last sample minus the margin for every project; otherwise `handoff_threshold`.
- [x] Board and web show the context below the threshold too, with the derived source; only high contexts count as context high.
- [x] Doctor prints the derived handoff, keeps the no-margin warning, and fails on an invalid `guild.json`.

## T13 — Handoff margin as a share and a floor above the session start

**Depends on:** T12
**Status:** [x] done — #173

**What:** with a 1M context window the automatic compaction lands around 21%, so the margin in points put the threshold below a fresh session's start and every respawned generation handed off at once. Decisión del dev, 2026-10-18: `handoff_margin` becomes a share of the last compaction, and each session's threshold is floored at its first nonzero reading plus 5.

**Acceptance:**
- [x] With `handoff_margin` and a sample, the threshold is the sample minus that share of it, rounded down.
- [x] The statusline keeps the first nonzero reading per session; the threshold never sits below it plus 5, and the board and web name that source.
- [x] Doctor warns when the derived handoff sits within 5 points of the latest session start.
- [x] `ctx-baseline` markers are pruned with the other state markers.

## T14 — Revive from the main checkout when the worktree is gone

**Depends on:** —
**Status:** [x] done — #174

**What:** `revive` gives a party whose recorded cwd no longer exists (a removed worktree) the nearest main checkout above that cwd, and launches it `fresh`, since its transcript cannot be resumed from another directory. Without such a checkout the party is still skipped with the reason.

**Acceptance:**
- [x] A removed worktree under a main checkout launches the next generation fresh from that checkout.
- [x] `--list` shows the checkout as cwd and `fresh`.
- [x] A missing cwd with no main checkout above it is still skipped.

## T15 — Idle compactions leave no compaction sample

**Depends on:** T12
**Status:** [x] done — #175

**What:** `PreCompact` with trigger `auto` also fires on Claude Code's idle compaction, which runs on a quiet session long before the context limit. The hook skips the sample when the statusline percentage is 30 minutes old or more, so the handoff threshold follows only context-limit compactions.

**Acceptance:**
- [x] A pre-compact whose statusline percentage is 30 minutes old or more records nothing.
- [x] A pre-compact right after activity still records the percentage.

## T16 — Handoff chain keeps permission mode and auto-respawn

**Depends on:** T10
**Status:** [x] done

**What:** A generation relaunched by pasting the printed command lost the permission mode (`SessionStart` does not receive it) and had no recorded window, so the chain stayed manual. `UserPromptSubmit` now records the mode, `guild handoff` carries it, `SessionStart` adopts the current tmux window of the `guild` session, and a plain handoff prints `guild revive --party <party>` before the raw command. Decisión del dev, 2026-11-09.

**Acceptance:**
- [x] A `UserPromptSubmit` with a permission mode records it for the leader.
- [x] `guild handoff` without `--respawn` prints the recorded mode in the raw command.
- [x] A `SessionStart` from a pane in the `guild` session with no recorded window records that window; a pane elsewhere records nothing.
- [x] A plain handoff prints `guild revive --party <party>` first and the raw command as fallback; without tmux it prints the raw command only.
- [x] The nudge of a generation without a recorded window says auto-respawn is off and points to the revive command.

## T17 — Lean compaction summary and brief after compaction

**Depends on:** T15
**Status:** [x] done

**What:** `PreCompact` prints instructions for a bound session (leader or adventurer) so the summary keeps only in-flight state: task ref, running subagents and background commands with ids, waits, uncommitted or unpushed work and open decisions. `SessionStart` with source `compact` injects the leader's task brief and party memory before the handoff nudge. Decisión del dev, 2026-11-09.

**Acceptance:**
- [x] A pre-compact of a bound session prints the summary instructions and still records the percentage.
- [x] A pre-compact of an unbound session prints nothing.
- [x] A `SessionStart` with source `compact` of a bound leader prints the task brief and memory, then the nudge.

## T18 — Session names say who the session is

**Depends on:** T16
**Status:** [x] done

**What:** The `UserPromptSubmit` hook titles a bound session `<party>-g<N>` or `adventurer <id>` when its name was generated by Claude Code, and the leader row records that title. Health job and solo player sessions launch as `health-<job>-YYYYMMDD-HHMMSS`, with the tmux window name unchanged. Decisión del dev, 2026-11-10.

**Acceptance:**
- [x] A bound session with a generated name receives its title on the next prompt, with the usual context still delivered.
- [x] A name set by the human, a collision name, a session already titled and an unbound session receive no title.
- [x] Two runs of a health job or solo player get different session names and keep one window name.
