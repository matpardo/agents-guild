---
epic: item-dates
type: spec
title: Dates on every item
status: active
owner: matpardo
created: 2026-10-24
updated: 2026-10-24
---

# Spec: Dates on every item

## Goal

Every item a person or a session creates through a command shows when it was created and, if it changed later, when it last changed, in the CLI and the web.

## Problem

Ideas show their dates, but quests, tasks, claims, parties, asks and adventurers show few or none. Without them the human cannot tell what is stale.

## Scope

An item that the human or a session creates through a command, and that the CLI or the web shows as its own card, row or line block, shows when it was created and, if it changed later, when it last changed. The label is `created X · updated Y` (minute precision, local time), built from stored event timestamps.

| Entity | Dates | State |
|---|---|---|
| Ideas | created, updated | done |
| Quests | created, updated | T01 |
| Quest tasks | created, updated | T01 |
| Tracked PRs | tracked at, last activity | T02 |
| Claims | claimed at | T02 |
| Parties | started at, last change | T02 |
| Asks | created, answered | T03 |
| Adventurers | started, done | T03 |
| Notices | already complete | done |

Rows stored before a date column existed show no date until the log is replayed: run `guild compact`, then `guild rebuild`, once, with no session working. `guild doctor` warns while such rows remain.

## Out of scope

- Mirrors of outside systems: SDD epics, SDD tasks and tracker cards.
- Links, pins, process state, samples, cursors and memory.

## Success criteria

- [ ] Each entity in the table shows its dates in the CLI and the web.
- [ ] Stored dates are equal before and after `guild rebuild`.
- [ ] Output hides the label when a date is unknown.

## Security and data

Dates come from the event timestamps only. No new input and no new write path.
