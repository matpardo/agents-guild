---
epic: core-layering
type: tasks
title: Core write consistency and module layering
status: done
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

## T03 — Keep core modules free of command imports

**Depends on:** T02
**Status:** [x] done

**What:** move the queries that core modules took from command modules into core modules (`raid_members`, `notices`, `ideas`, `cards`, `transcripts`, `statusline_state`, `main_status`, `pr_records`, `work_queue` and `scoped_queue` in `merge_queue`), so the hook path no longer imports command modules.

- `tests/test_layering.py` fails when a module outside `guild/commands/`, `guild/cli.py` and `guild/webserver.py` imports `guild.commands`, and names the module and what it imports.
- Callers and tests use the core modules directly, with no re-export left in the command modules.
- Command behavior and signatures are unchanged.
- The full suite, `ruff check` and `ruff format --check` pass.

## T04 — Validate event payloads on record

**Depends on:** —
**Status:** [x] done

**What:** declare the payload keys each event kind requires next to its reducer in `guild/reducers.py` and make `events.record` refuse an unknown kind or a payload lacking a required key before the event is written; `guild rebuild` replays stored events without validation.

- A payload missing a required key, or an unknown kind, raises `GuildError` naming the kind and writes no event row.
- `tests/test_event_payload_validation.py` parses `guild/reducers.py` and fails when the declared keys of any kind differ from the keys its reducer and helpers read with `payload["key"]`.
- Legacy stored events stay replayable by `guild rebuild`.
- The full suite, `ruff check` and `ruff format --check` pass.
