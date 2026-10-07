---
epic: keep-moving
type: spec
title: Keep work moving without the human
status: done
owner: matpardo
created: 2026-09-27
updated: 2026-10-07
---

# Spec: Keep work moving without the human

## Goal

Agents know what to do next, in what order, and hand off to a fresh session before their context runs out.

## Problem

Sessions stop to ask "what should I review next?" and die when their context fills. The plan lives in SDD `tasks.md`, which guild could not read.

## Scope

- `sync --source sdd`: observed epics and tasks from explicit per-project regexes.
- `guild next`: ranked next action (PRs marked `fixes-main` or `fixes-flaky` first, then PR problems, answered asks, stale PRs, next task by order with dependencies done).
- Done-ness precedence guild > tracker > SDD, with disagreements shown.
- Handoff at a context threshold; resume by party; resume from a terminal by session name.
- `PostToolUse` hook so busy sessions see answers mid-turn.

## Out of scope

- Tracker adapter and the `drift` report (`three-way-tracking`).
- Waking idle sessions (see decision `20260928_idle-wake-no-go`).

## Success criteria

- [x] 49 of 50 real epics parse; the remaining one was a legacy format, since migrated.
- [x] `guild next` answers with the item a human would pick on real data.
- [x] Migration verified on a copy of a live database.

## Security and data

SDD content is external text that reaches agents; framed as data in `security-hardening`.
