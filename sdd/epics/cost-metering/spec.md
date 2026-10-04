---
epic: cost-metering
type: spec
title: Measure what each party costs
status: draft
owner: matpardo
created: 2026-10-04
updated: 2026-10-04
---

# Spec: Measure what each party costs

## Goal

`guild cost` reports token usage by session, party, quest, task and model, so every other change can prove its savings.

## Problem

A three-day sample of the first raid showed output is 0.1–0.3% of the volume: the cost is long sessions re-reading their context every turn. Nothing in guild shows this today, so no change to session length, model choice or review rounds can be verified.

## Scope

- Read `message.usage` and `message.model` from Claude Code transcripts (sessions and subagents), with a per-transcript byte-offset cursor so re-runs are incremental.
- Map session to party through the event log; attribute to a task by the `task.started`–`task.done` window.
- Store one `cost.sampled` local event per session, day and model (aggregate, never per message).
- `guild cost [--since] [--by session|party|model|quest|task] [--project]`.

## Out of scope

- Budgets and accounts per execution profile (`budgets`, `execution-profiles`).

## Success criteria

- [ ] The totals for one session match a manual sum over its transcript.
- [ ] A second run over unchanged transcripts adds no event.

## Security and data

Transcripts hold full conversations; only the `usage` and `model` fields are read and nothing else is stored.
