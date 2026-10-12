---
epic: session-autopilot
type: spec
title: Guild-launched sessions end themselves and hand off
status: draft
owner: matpardo
created: 2026-10-12
updated: 2026-10-12
---

# Spec: Guild-launched sessions end themselves and hand off

## Goal

A session that guild launched ends with a handoff even when the agent forgets, crashes or waits, so the dispatcher can always launch the party's next generation. A human can stop all dispatch at once.

## Problem

A party whose session ends without `guild handoff` stays `active`; the dispatcher skips it ("did not hand off") until a human revives it. A dispatched session that finishes its turn sits idle with a live pid, so every trigger for it is deferred and dropped after 24h. There is no way to stop the dispatcher for all projects at once, and lifecycle failures point at a history view that does not show them.

## Scope

- Automatic handoff: guild writes a handoff from its own state (active task, PRs, open asks, notices, claims) and the party leader session's worktree (branch, count of uncommitted files, count of unpushed commits; no file names). `Learned` reads "none (automatic handoff)"; the event carries `auto: true`. A human can hand off a party whose leader session is gone, from a terminal or the web.
- The dispatcher hands off, before evaluating rules, every active party whose current generation runs in a guild-recorded window, whose party leader session process is gone and whose window is closed.
- Stop hook, in a guild-recorded window that received no human prompt after its launch prompt: the first stop is blocked once with a request to finish or run `guild handoff --close`; a second stop writes the automatic handoff and closes the pane. Skipped while the transcript shows a usage limit.
- Breaker: after two automatic handoffs in a row the dispatcher skips the party with a notice until a human revives it.
- `SessionEnd` records `session.ended`, so the board stops showing a stale status.
- `guild dispatch pause --reason` and `guild dispatch resume`, and the same in the web: while paused, launches are deferred and promote, announce and nudge do nothing. Any session can pause; only a human (no session) can resume.
- `guild history` and the web history show failed lifecycle runs with their last output line.

## Out of scope

- Sessions a human started: they keep today's skip and notice.
- Relaunch on permission waits: they are resolved in the pane; the push notification stays.
- Deferring on red main: the pre-push hook and ready-check already gate on it.
- Fixing a project's lifecycle command (environment, outside guild).
- Depends on dispatcher T10 (`handoff --close`) for the pane close.

## Success criteria

- [ ] A guild-launched session killed mid-task is relaunched for the same task without a human.
- [ ] A guild-launched session whose ask is open ends with a handoff and is relaunched when the ask is answered.
- [ ] A session a human typed into is never closed by guild.
- [ ] A pause stops every launch and gh write; after resume, deferred triggers launch.
- [ ] A failed lifecycle run shows its last output line in `guild history`.

## Security and data

The automatic handoff holds only guild state and git counts, never tool output or file names; it is a local file framed as data when injected. The pause reason passes `validate_field`. Lifecycle output stays in local events and is never copied into notices, which are broadcast and exportable. A pane is closed only for the window guild recorded for that generation.

## Decisions

- Autopilot applies only to sessions in a guild-recorded window (decisión del dev, 2026-10-12). "Leader" means the party's leader session; a raid lead is a different role and plays no part here.
- No red-main gate on dispatch (decisión del dev, 2026-10-12).
