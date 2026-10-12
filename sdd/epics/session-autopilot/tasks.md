---
epic: session-autopilot
type: tasks
title: Guild-launched sessions end themselves and hand off
status: active
updated: 2026-10-12
---
# Tasks: Guild-launched sessions end themselves and hand off

## T01 — Global dispatch pause

**Depends on:** —
**Status:** [x] done — #135

**What:** events `dispatch.paused` and `dispatch.resumed` with a one-row reducer. `Launcher.evaluate` returns busy "dispatch paused" through the existing defer path; promote, announce and nudge do nothing while paused. `dispatch status` shows it. Resume refuses when a session id is set. Web button and reason field post through `sendPost` to the same functions. README and GUILD.md updated.

## T02 — Lifecycle failures readable

**Depends on:** —
**Status:** [x] done — #144

**What:** `guild history` and the web history list failed, timed-out and errored `lifecycle.ran` events with their last non-empty output line on one line. Output never enters notices.

## T03 — Automatic handoff writer

**Depends on:** —
**Status:** [x] done — #145

**What:** `handoff.write_auto(ctx, binding)` reuses `_render_handoff` and `_write_handoff`, adds `auto: true` to the event, and adds git counts (branch, dirty, unpushed) via the existing git helpers. `guild handoff --party <p>` from a terminal only, and a web "Hand off" action for a party whose leader session is gone.

## T04 — Dispatcher hands off dead party leader sessions

**Depends on:** T03
**Status:** [x] done — #146

**What:** one step in `dispatch._pass` after `reconcile`: party active, recorded window present, party leader session not live, window gone → `write_auto`. Adds an ADR amending `20261004_dispatcher-launches-fresh-sessions`.

## T05 — Stop hook wraps up unattended sessions

**Depends on:** T03
**Status:** [x] done — #148

**What:** the Stop hook wraps up a session only when `GUILD_RESUME` (or, for a session that already ran a plain `guild handoff`, the leader/party join) names the party it is bound to, the party is not a keeper, there is no pending background work, nobody has typed a real prompt (`attended-<session>` marker, written by `prompt-submit` for anything but guild's own resume prompt or a `<task-notification>` report) and the transcript shows no usage limit. The first stop prints a block decision once and records a `wrapup-<session>` marker; the next stop (by `stop_hook_active` or the marker alone) runs `write_auto` and closes the recorded pane with `tmux_windows.closable_pane` (moved there from `handoff.py`, now shared with `--close`/`--respawn`). A session already `awaiting-leader` from a plain handoff gets its pane closed too, without a second handoff. `attended-` and `wrapup-` markers join the prune pattern.

## T06 — Automatic-handoff breaker

**Depends on:** T04
**Status:** [ ] pending

**What:** the dispatcher skips with a notice when the party's last two handoffs were automatic, following the existing launch breaker.

## T07 — SessionEnd records the end

**Depends on:** —
**Status:** [ ] pending

**What:** wire `SessionEnd` in `claude_settings.py`, doctor and wire-settings; record `session.ended` with its reducer; remove the outdated README line.
