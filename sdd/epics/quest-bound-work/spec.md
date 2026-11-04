---
epic: quest-bound-work
type: spec
title: A party's work always belongs to a quest
status: done
owner: matpardo
created: 2026-10-23
updated: 2026-11-04
---

# Spec: A party's work always belongs to a quest

## Goal

Every PR a party opens belongs to one of its quest tasks, so the board never shows party PRs outside active tasks.

## Problem

`guild pr track --card` lets a party track a PR with no task. The board then lists it under "PRs outside active tasks", where nobody follows it as planned work. Loose work is a one-off job, which is what an adventurer is for (see `adventurers`).

## Scope

- `guild pr track` from a party refuses without `--task`. The error points to `guild task add` on an open quest of the party, or `guild quest add --no-epic`.
- `--card` is accepted only from an adventurer with a free job. An adventurer on a task tracks with `--task`.
- PRs already tracked loose stay on the board until they merge or close; nothing creates new ones. Adventurer PRs show under the adventurer.
- `guild pr track --card` on an existing PR keeps working for the card key of a task-bound PR.
- `guild task add --no-sdd` marks housekeeping work with no entry in the epic `tasks.md`; drift and the epic `quest done` gate skip it, and the board marks it.
- `README.md` and `GUILD.md` change with the code.

## Out of scope

- Moving existing loose PRs to tasks automatically.

## Success criteria

- [x] A party cannot track a new PR without a task, from the CLI or the web.
- [x] An adventurer tracks a PR with `--task` or `--card`.
- [x] Old loose PRs still show and replay in `guild rebuild`.

## Security and data

Validation only; no new data. The error text names commands, never PR titles.
