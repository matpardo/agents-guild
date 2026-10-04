---
epic: budgets
type: spec
title: Token and round budgets per task
status: draft
owner: matpardo
created: 2026-10-04
updated: 2026-10-04
---

# Spec: Token and round budgets per task

## Goal

A task that reaches its token or review-round budget stops and asks instead of continuing.

## Problem

One PR in the first raid went through eight review rounds; from the fourth on only optional findings remained. There is no cap and no cut-off criterion.

## Scope

- Per-task budget in tokens (from `cost-metering`) and in review rounds.
- On reaching it, guild creates an ask for the party with the spend so far and the options (continue, cut, change model).

## Out of scope

- Enforcing budgets inside a running session beyond hook messages.

## Success criteria

- [ ] A task over budget produces exactly one ask and `guild next` stops offering it until answered.

## Security and data

N/A beyond usage figures.
