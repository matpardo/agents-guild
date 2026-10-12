---
epic: session-autopilot
type: tasks
title: Guild-launched sessions end themselves and hand off
status: draft
updated: 2026-10-12
---
# Tasks: Guild-launched sessions end themselves and hand off

## T01 — Global dispatch pause

**Depends on:** —
**Status:** [ ] pending

**What:** events `dispatch.paused` and `dispatch.resumed` with a one-row reducer. `Launcher.evaluate` returns busy "dispatch paused" through the existing defer path; promote, announce and nudge do nothing while paused. `dispatch status` shows it. Resume refuses when a session id is set. Web button and reason field post through `sendPost` to the same functions. README and GUILD.md updated.

## T02 — Lifecycle failures readable

**Depends on:** —
**Status:** [ ] pending

**What:** `guild history` and the web history list failed, timed-out and errored `lifecycle.ran` events with their last non-empty output line on one line. Output never enters notices.

## T03 — Automatic handoff writer

**Depends on:** —
**Status:** [ ] pending

**What:** `handoff.write_auto(ctx, binding)` reuses `_render_handoff` and `_write_handoff`, adds `auto: true` to the event, and adds git counts (branch, dirty, unpushed) via the existing git helpers. `guild handoff --party <p>` from a terminal only, and a web "Hand off" action for a party whose leader session is gone.

## T04 — Dispatcher hands off dead party leader sessions

**Depends on:** T03
**Status:** [ ] pending

**What:** one step in `dispatch._pass` after `reconcile`: party active, recorded window present, party leader session not live, window gone → `write_auto`. Adds an ADR amending `20261004_dispatcher-launches-fresh-sessions`.

## T05 — Stop hook wraps up unattended sessions

**Depends on:** T03
**Status:** [ ] pending

**What:** needs dispatcher T10 merged. The Stop hook honors `stop_hook_active` and prints a block decision once; the second stop runs `write_auto` and closes the recorded pane. Marker files for "launch prompt seen" and "attended" join the prune pattern. Skipped on a usage limit.

## T06 — Automatic-handoff breaker

**Depends on:** T04
**Status:** [ ] pending

**What:** the dispatcher skips with a notice when the party's last two handoffs were automatic, following the existing launch breaker.

## T07 — SessionEnd records the end

**Depends on:** —
**Status:** [ ] pending

**What:** wire `SessionEnd` in `claude_settings.py`, doctor and wire-settings; record `session.ended` with its reducer; remove the outdated README line.
