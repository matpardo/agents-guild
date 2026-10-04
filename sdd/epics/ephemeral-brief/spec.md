---
epic: ephemeral-brief
type: spec
title: Short sessions started from a task brief
status: done
owner: matpardo
created: 2026-10-04
updated: 2026-10-04
---

# Spec: Short sessions started from a task brief

## Goal

A fresh session can pick up one task from a compact brief, so parties run as short sessions instead of one long one.

## Problem

Long sessions re-read hundreds of thousands of tokens per turn. A party is identity and state in guild, not a live process, but there is no task-scoped brief to start a fresh session from; the per-session `brief` only describes the current binding.

## Scope

- `guild brief <party>/<quest>/<tid>` from a terminal: task, PR and its review comment counts, open and answered asks, targeted notices, claims, last handoff. Guild stores only the review comment count and how many were already notified, so the brief shows `review comments: N (M unseen)`, not threads.
- `revive` and handoff resume commands use it as the prompt.
- `revive` and handoff resume: the `SessionStart` injection of a fresh generation carries the task brief.
- A party without a live session is a normal state: display statuses `idle` and `queued` replace `awaiting-leader` and `unknown` for it; vocabulary amended (decision of the dev, 2026-10-04).
- Recommend a lower `handoff_threshold` (40) in the docs.

## Out of scope

- Launching sessions automatically (`dispatcher`).

## Success criteria

- [x] A session started from a task brief needs no further state commands to begin the task.
- [x] A party with no live session never shows `unknown`.

## Security and data

The brief is local text injected as data, framed like other inbox content. Every dynamic field is stripped of control sequences and single-lined; the brief is capped at 4000 characters with explicit truncation markers; it is read-only (no cursor, no acknowledgement, no event).
