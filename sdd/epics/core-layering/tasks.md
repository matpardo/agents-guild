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

## T02 — Break the claim, quest and sync import cycle

**Depends on:** —
**Status:** [x] done

**What:** move the task holder queries (`adventurer_holder`, `task_adventurer`, `open_quest_holder`, `reject_taken_tasks` and their helpers) from the quest command into the core module `guild/task_holders.py`, so `claim` no longer imports `quest` and the claim, quest and sync import loop is gone.

- `guild/task_holders.py` imports nothing from `guild.commands`, and every caller uses it directly with no re-export left in the quest command.
- `tests/test_import_cycles.py` fails on any import cycle among `guild` modules and names the modules in it.
- Command behavior and signatures are unchanged.
- The full suite, `ruff check` and `ruff format --check` pass.
