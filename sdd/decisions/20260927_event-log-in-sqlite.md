# ADR: Append-only event log in SQLite

- **Date:** 2026-09-27
- **Status:** accepted

## Context

Several Claude Code sessions write coordination state at the same time. Agents must not write state by hand into markdown: "a guard written in prose does not stop a command". State must be reproducible and, later, shareable across machines.

## Decision

Python 3.10 standard library only. One SQLite database in WAL mode (`busy_timeout=5000`, writes in `BEGIN IMMEDIATE`). Every write appends an event and applies a reducer to projection tables in the same transaction; `guild rebuild` replays events. Events carry `origin` and `visibility` from day one so federation is an export/import of events.

## Consequences

- No dependencies to install; concurrency handled by SQLite.
- Schema changes need explicit migrations and reducers tolerant of legacy payloads (learned when a live DB carried pre-migration `pr.synced` events).
- Reads are cheap enough for hooks (< 100 ms end to end).
