---
epic: derived-state
type: spec
title: Flags that follow the events that resolve them
status: done
owner: matpardo
created: 2026-10-04
updated: 2026-10-11
---

# Spec: Flags that follow the events that resolve them

## Goal

PR flags and repository health come from events, so they never go stale.

## Problem

`needs-ask-answer` is set and cleared by hand, and answering the ask never clears it; stale flags misled the raid lead and the merge queue. A red main is shown, but nothing stops a push on top of it.

## Scope

- `needs_ask_answer` set while an open ask refs the PR, cleared when it is answered or dismissed; the manual flag stays as an override.
- Pre-push hook refuses a push while the project's main is red, except for the branch that fixes it.
- Merge queue marks the PR to fix first; flags with no backing event expire.

## Out of scope

- Typed notices for agents (phase 1).

## Success criteria

- [x] Answering an ask clears the flag on its PR without a `pr set`.
- [x] A push while main is red is refused with the reason and the way out.

## Security and data

N/A beyond existing PR data.
