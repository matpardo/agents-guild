---
epic: dispatcher
type: spec
title: React to events without a watching session
status: active
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

- `guild dispatch run [--dry-run]` and `guild dispatch status`, run by their own timer under a lock, with a cursor per project that starts at the newest event when the project enables the dispatcher, is dropped when it disables it, and ignores triggers older than one hour.
- A `dispatcher` config block per project: `permission_mode` (`manual`, `acceptEdits` or `auto`), `max_launches_per_hour` and `rules`, each `dry-run` or `on`.
- Rules: answered ask → launch the asking party; failing checks on a head commit → launch the PR owner pointing at the failing checks; converged and green PR → mark it ready and notify (later); merged PR → tell the next in the queue to rebase (later).
- A launch starts the next generation of a handed-off party in the existing `guild` tmux session with the handoff resume command and a prompt that names the trigger by id only.
- Never launch a party with a live session, an open window, a launch in flight, a paused raid, a keeper, or a previous launch that never bound; at most `max_launches_per_hour` per project.
- Every decision is a local `dispatch.*` event, decided once per trigger; failures post a project notice and run `notify.command`.
- Decision `20261004_dispatcher-launches-fresh-sessions`.

## Out of scope

- Waking idle sessions (decision `20260928_idle-wake-no-go`).
- Moving lifecycle commands (`lifecycle-commands`) under the dispatcher: they stay in `sync` and are revisited with `officers`.
- CI logs in the prompt.
- Creating the tmux session or launching a party that did not hand off.
- Token budgets (`budgets`).

## Success criteria

- [ ] In dry-run, every rule prints the action it would take on recorded events.
- [ ] An answered ask on an enabled project launches exactly one session for that party.
- [ ] A second pass or a restart never launches twice for the same trigger.
- [ ] A launch not bound within 10 minutes is reported once and blocks the party until resumed by hand.

## Security and data

Launching sessions spends money and runs code with the user's permissions. Rules are opt-in per project and per rule, dry-run until `on`, recorded as local events, limited to one live launch per party and to a maximum per hour, and decided at most once per trigger because the intent is recorded before the launch. The prompt carries ids only. `bypassPermissions` and `dontAsk` cannot be configured and the launched mode never exceeds the configured one. The dispatcher never writes to an existing session and never starts the tmux server. Marking a PR ready is the only GitHub write and is its own opt-in rule (later). Notices carry party names and ids only.
