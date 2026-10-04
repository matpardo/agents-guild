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
