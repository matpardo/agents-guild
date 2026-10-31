---
epic: core-layering
type: spec
title: Core write consistency and module layering
status: active
owner: matpardo
created: 2026-10-31
updated: 2026-10-31
---

# Spec: Core write consistency and module layering

## Goal

Make every state change check its preconditions under the write lock, and give the modules a one-way dependency order, so concurrent sessions cannot corrupt state and the import graph stays acyclic.

## Problem

Commands read state and validate it before opening the write transaction, so two sessions that race both pass the same check and the second write silently overwrites the first (an area claim is stolen, an open item is taken twice). The command modules also import each other in a cycle, core modules import from `guild.commands`, and `events.record` accepts any payload shape, so a missing key surfaces only when a reducer fails.

## Scope

- Check-then-write races: reads that decide the outcome of a write run inside the same `BEGIN IMMEDIATE` transaction as the write; slow work (subprocess, network) stays before the transaction and only the cheap database condition is re-checked inside it.
- Break the import cycle `commands.claim` → `commands.quest` → `commands.sync` → `commands.claim`.
- Core modules (everything outside `guild/commands`, `guild/cli.py` and `guild/webserver.py`) must not import `guild.commands`.
- Validate the required payload keys of each event kind in `events.record`.

## Out of scope

- Typed row and event dataclasses.
- Splitting `reducers.py` by aggregate.

## Success criteria

- [ ] Every command that checks ownership, exclusivity or state before a write has a test where a competing write lands just before the transaction and the command is refused.
- [ ] No import cycle among `guild/commands` modules.
- [ ] No core module imports `guild.commands`, guarded by a test.
- [ ] `events.record` rejects an event whose payload lacks a required key.

## Security and data

Touches the local SQLite event log and its reducers only. The race fixes keep the exclusivity guarantees that area, task and ownership checks give; a refused write raises the same errors as today and rolls back. No new inputs and no new trust boundary.
