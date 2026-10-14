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
