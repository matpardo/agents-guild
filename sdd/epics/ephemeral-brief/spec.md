---
epic: ephemeral-brief
type: spec
title: Short sessions started from a task brief
status: draft
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

- `guild brief <party>/<quest>/<tid>` from a terminal: task, PR and its open threads, open and answered asks, targeted notices, last handoff.
- `revive` and handoff resume commands use it as the prompt.
- Recommend a lower `handoff_threshold` (40) in the docs.

## Out of scope

- Launching sessions automatically (`dispatcher`).

## Success criteria

- [ ] A session started from a task brief needs no further state commands to begin the task.

## Security and data

The brief is local text injected as data, framed like other inbox content.
