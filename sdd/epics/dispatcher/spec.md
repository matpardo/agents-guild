---
epic: dispatcher
type: spec
title: React to events without a watching session
status: draft
owner: matpardo
created: 2026-10-04
updated: 2026-10-04
---

# Spec: React to events without a watching session

## Goal

A deterministic dispatcher reads guild events and either acts on its own or launches a fresh session with a brief, so nothing waits for a human to give a turn.

## Problem

Communication is pull-only: answered asks, red CI and merged PRs reach a party only when someone gives it a turn. Leaders spend tokens polling state that a script could watch.

## Scope

- `guild dispatch [--dry-run]`, run by the sync timer, with its own event cursor.
- Rules: answered ask → launch the asking party on that task; failing checks → launch the PR owner with the filtered log; converged and green PR → mark it ready and notify; merged PR → tell the next in the queue to rebase.
- Opt-in per project and per rule; dry-run unless enabled; never launch a party whose session is working (`session-liveness`).
- Decision `20261004_dispatcher-launches-fresh-sessions`.
- Lifecycle commands (`lifecycle-commands`) run from `guild sync --source gh` today; they move under the dispatcher when it lands, reusing the same runner and lock.

## Out of scope

- Waking idle sessions (decision `20260928_idle-wake-no-go`).

## Success criteria

- [ ] In dry-run, every rule prints the action it would take on recorded events.
- [ ] An answered ask on an enabled project launches exactly one session for that party.

## Security and data

Launching sessions spends money and runs code with the user's permissions: rules are opt-in, logged as events, and limited to one live launch per party.
