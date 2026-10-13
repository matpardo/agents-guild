---
epic: session-autopilot
type: tasks
title: Sessions run in tmux, launched by the human
status: done
updated: 2026-10-13
---
# Tasks: Sessions run in tmux, launched by the human

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

## T08 — Remove the dispatcher automatic handoff

**Depends on:** —
**Status:** [x] done — #149

**What:** delete the dispatcher pass that writes an automatic handoff for a dead leader, its tests, the decision amendment and the docs; `write_auto` and `run_for_party` stay.

## T09 — Revive starts handed-off parties

**Depends on:** —
**Status:** [x] done — #150

**What:** `guild revive` also lists and launches `awaiting-leader` parties, always with the fresh next-generation command, never `--resume`.

## T10 — Dispatcher suggests instead of launching

**Depends on:** T09
**Status:** [x] done — #151

**What:** the dispatcher tells the human to run `guild revive --party <party>` instead of launching a session, and `limit_resume` posts a notice instead of typing into a window. Decision `20261012_dispatcher-suggests-human-launches`.

## T11 — Respawn only for keeper parties

**Depends on:** —
**Status:** [x] done — #152

**What:** `guild handoff --respawn` is refused for non-keeper parties and the context nudge asks for it only from keepers; every other party gets the plain handoff nudge and the human relaunches with `guild revive`.

## T12 — Rescope the epic to human-launched sessions

**Depends on:** —
**Status:** [x] done — #153

**What:** rewrite the spec to "the human launches, guild suggests", drop the Stop-hook wrap-up, breaker and SessionEnd tasks, and close the epic.
