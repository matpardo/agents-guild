---
epic: core-layering
type: tasks
title: Core write consistency and module layering
status: active
updated: 2026-10-31
---

# Tasks: Core write consistency and module layering

## T01 — Run state checks inside the write transaction

**Depends on:** —
**Status:** [x] done

**What:** move the reads that decide a write into the same `BEGIN IMMEDIATE` transaction as the event record for area claim and release, open-item take, adventurer start, task add, start, block, done and move, ask answer and dismiss, and the create and finish commands of work groups; slow work stays before the transaction.

- A test per command lands a competing write just before the transaction and expects the command to be refused with its existing error.
- Duplicate-safe commands (primary key rejects the second write, or the outcome is idempotent) are left unchanged.
- The full suite, `ruff check` and `ruff format --check` pass.
