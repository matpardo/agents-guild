---
epic: session-autopilot
type: spec
title: Sessions run in tmux, launched by the human
status: done
owner: matpardo
created: 2026-10-12
updated: 2026-10-14
---

# Spec: Sessions run in tmux, launched by the human

## Goal

No session starts or wakes on its own. The human launches every session in tmux; guild tells the human which party has something to do, writes handoffs on request, and lets the human stop all dispatch at once.

## Problem

The dispatcher launched sessions by itself and a Stop hook was planned to close idle ones, but that behavior could not be checked from inside a session, while watching the tmux windows gave the feedback the human needed. A party that handed off could not be started with `guild revive`, `limit_resume` typed into live windows, and lifecycle failures pointed at a history view that did not show them.

## Scope

- `guild dispatch pause --reason` and `guild dispatch resume`, and the same in the web.
- `guild history` and the web history show failed lifecycle runs with their last output line.
- `guild handoff --party` and the web "Hand off" button write a handoff for a party whose leader session is gone; `guild handoff --close` closes a guild-launched pane after a handoff.
- `guild revive --party X` starts a party that handed off, as a fresh generation in tmux.
- The dispatcher suggests instead of launching: a notice and a push say "X ready to resume: run guild revive --party X"; `limit_resume` only notifies.
- `guild handoff --respawn` only for keeper parties.

## Out of scope

- Automatic handoffs for dead sessions, a Stop hook that blocks or closes panes, an automatic-handoff breaker and a `SessionEnd` record: dropped with the decision below.

## Success criteria

- [x] No guild code path creates a tmux window or types into one without a human command (keeper respawn excepted).
- [x] A handed-off party starts again with `guild revive --party X`.
- [x] A pause stops every suggestion and gh write; after resume, deferred triggers are suggested.
- [x] A failed lifecycle run shows its last output line in `guild history`.

## Security and data

Handoffs written for a party hold only guild state and git counts, never tool output or file names. The pause reason passes `validate_field`. Lifecycle output stays in local events and never enters notices. A pane is closed only for the window guild recorded for that generation.

## Decisions

- Sessions are launched by the human in tmux; the dispatcher only suggests (decisión del dev, 2026-10-12). See `sdd/decisions/20261012_dispatcher-suggests-human-launches.md`.
- `--respawn` stays for keeper parties only (decisión del dev, 2026-10-12).
- No red-main gate on dispatch (decisión del dev, 2026-10-12).
- Dispatch pause was removed together with the dispatcher (decisión del dev, 2026-10-14). See `sdd/decisions/20261014_board-shows-waits-no-dispatcher.md`.
