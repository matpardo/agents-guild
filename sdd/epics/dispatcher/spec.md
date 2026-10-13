---
epic: dispatcher
type: spec
title: React to events without a watching session
status: active
owner: matpardo
created: 2026-10-04
updated: 2026-10-12
---

# Spec: React to events without a watching session

## Goal

A deterministic dispatcher reads guild events and either acts on its own or tells the human which party is ready to resume, so nothing waits unseen for a turn.

## Problem

Communication is pull-only: answered asks, red CI and merged PRs reach a party only when someone gives it a turn. Leaders spend tokens polling state that a script could watch.

## Scope

- `guild dispatch run [--dry-run]` and `guild dispatch status`, run by their own timer under a lock, with a cursor per project that starts at the newest event when the project enables the dispatcher, is dropped when it disables it, and ignores triggers older than one hour.
- A `dispatcher` config block per project with `rules`, each `dry-run` or `on`.
- Rules: answered ask → suggest a revive of the asking party; failing checks on a head commit → suggest a revive of the PR owner; converged and green PR → mark it ready and notify (later); merged PR → tell the next in the queue to rebase (later).
- A suggestion is a project notice `<party> ready to resume (<rule> <subject>): run guild revive --party <party>` and a `notify.command` run; the human launches the session with `guild revive`.
- Never suggest a party with a live session, an open window or a paused raid: the trigger is deferred, kept pending and retried every pass for 24 hours. Never suggest a keeper or a closed party.
- Every decision is a local `dispatch.*` event, decided once per trigger; failures post a project notice and run `notify.command`.
- Decision `20261012_dispatcher-suggests-human-launches`, which supersedes `20261004_dispatcher-launches-fresh-sessions`.

## Out of scope

- Waking idle sessions (decision `20260928_idle-wake-no-go`).
- Moving lifecycle commands (`lifecycle-commands`) under the dispatcher: they stay in `sync` and are revisited with `officers`.
- CI logs in the prompt.
- Starting or waking any session: the human runs `guild revive`.
- Token budgets (`budgets`).

## Success criteria

- [ ] In dry-run, every rule prints the action it would take on recorded events.
- [ ] An answered ask on an enabled project suggests exactly one revive for that party and starts nothing.
- [ ] A second pass or a restart never suggests twice for the same trigger.

## Security and data

The dispatcher starts and writes to no session: it records local `dispatch.*` events, posts project notices and runs `notify.command`. Rules are opt-in per project and per rule, dry-run until `on`, and decided at most once per trigger. Marking a PR ready is the only GitHub write and is its own opt-in rule. Notices carry party names and ids only. CI output can carry text from whoever opened a PR, but it never reaches a command line or a prompt because the dispatcher launches nothing.
