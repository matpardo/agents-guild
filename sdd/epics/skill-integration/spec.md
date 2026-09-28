---
epic: skill-integration
type: spec
title: Workflow skills call guild
status: draft
owner: matpardo
created: 2026-09-27
updated: 2026-09-28
---

# Spec: Workflow skills call guild

## Goal

The skills that open PRs and sync epics register their results in guild without the agent remembering to.

## Problem

Agents only track PRs and tasks when a rule reminds them. The skills that create those artifacts (`/pr-create`, `/tracker-epic-sync`) already know every field guild needs.

## Scope

- `/pr-create` runs `guild pr track` when `guild` is installed.
- `/tracker-epic-sync` runs `guild sync --source sdd` after writing keys.
- Optional by construction: repos that do not use guild keep working.

## Out of scope

- Making guild a dependency of generated repos.

## Success criteria

- [ ] A PR opened through the skill appears on `guild board` with no extra step.

## Security and data

Skills pass titles and summaries only; same caps and screening apply.
