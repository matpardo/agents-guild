---
epic: party-waits
type: tasks
title: Show what each party waits on
status: active
updated: 2026-10-14
---

# Tasks: Show what each party waits on

## T01 — Waits per party on the board

**Depends on:** —
**Status:** [x] done — #158

**What:** `guild/party_waits.py` derives each party's waits from the projections; `guild board` prints a `waits on:` line and the web board renders one pill per wait.

**Acceptance:**
- [x] Each wait kind has a test; the board and the web model carry `waits`.

## T02 — Fast board and quiet client hang-ups

**Depends on:** T01
**Status:** [x] done — #163

**What:** the unseen waits read only `ask.answered` and `notice.created` events from SQL instead of decoding every event after each cursor, and `guild web` drops a response quietly when the browser has already hung up.

**Acceptance:**
- [x] An event of another kind is never decoded by the waits.
- [x] A client that hung up prints no traceback.
