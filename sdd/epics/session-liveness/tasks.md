---
epic: session-liveness
type: tasks
title: Every party shows whether it is working or stuck
status: done
updated: 2026-10-04
---

# Tasks: Every party shows whether it is working or stuck

## T01 — Session status projection

**Depends on:** —
**Status:** [x] done — #64

**What:** `session.waiting`, `session.stopped`, `session.working` events (local) and a `session_status` table (session, party, status, detail, since) maintained by reducers and replayed by `rebuild`.

**Acceptance:**
- [x] `rebuild` reproduces `session_status` from events.

## T02 — Notification and Stop hooks

**Depends on:** T01
**Status:** [x] done — #64

**What:** `guild hook notification` and `guild hook stop`; `post-tool-use` and `prompt-submit` record `session.working` only when the status changes.

**Acceptance:**
- [x] A hundred tool calls in a working session add no event.
- [x] Unbound sessions record nothing and never fail the hook.

## T03 — Derived party status

**Depends on:** T02
**Status:** [x] done — #64

**What:** one function derives the party status and its age from the leader session status, open asks, `next` and party state.

## T04 — Status on every surface

**Depends on:** T03
**Status:** [x] done — #64

**What:** board (blocked sessions in NEEDS YOU, status per party), web `/api/board`, statusline count, revive listing, raid lead inbox line on a member's permission wait.

## T05 — Push command

**Depends on:** T02
**Status:** [x] done — #64

**What:** optional project config `notify.command` (argv list), validated; the notification hook runs it once per waiting episode with party and wait type.

## T06 — Doctor and docs

**Depends on:** T02
**Status:** [x] done — #64

**What:** doctor checks the `Notification` and `Stop` hooks and warns on guild state commands that are not allow-listed; README hook section and `GUILD.md` updated.

## T07 — Unknown status for a silent session

**Depends on:** T03
**Status:** [x] done — #66

**What:** a party whose leader session never reported a status shows `unknown`, not `working`.

## T08 — Background work is not waiting input

**Depends on:** T03
**Status:** [x] done

**What:** a leader that is idle or stopped while its own `guild pr wait` or subagents run shows `waiting-background`, not `waiting-input`; markers are ephemeral files fed by `pr wait` and the `SubagentStart`/`SubagentStop` hooks.

## T09 — Background status cannot hide a stopped subagent or a dialog

**Depends on:** T08
**Status:** [x] done

**What:** a subagent marker is dropped once Claude Code's own subagent meta file says it finished, and an elicitation dialog maps to `waiting-permission` so background work cannot hide it.

## T10 — A subagent waiting on its own background work stays live

**Depends on:** T09
**Status:** [x] done

**What:** `subagent-stop` reads the subagent's own transcript; when a background command it launched has no finished notification, the marker is kept with a waiting content that stays live regardless of the meta file, so an idle leader shows `waiting-background` instead of `waiting-input` until the subagent wakes and stops with nothing pending.
