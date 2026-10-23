---
epic: party-identity
type: spec
title: A session leads one party for its whole life
status: done
owner: matpardo
created: 2026-10-23
updated: 2026-10-23
---

# Spec: A session leads one party for its whole life

## Goal

A session never switches identity, so every quest, PR and claim it records belongs to the party it started with.

## Problem

A bound session can run `guild party start` or `guild party resume` for a second party. The reducer sets the new party's leader and never clears the old one, so both parties stay active with the same leader session and `resolve_binding` returns whichever row SQLite gives first. Work then lands on the wrong party. It happened once.

## Scope

- `guild party start` and `guild party resume` refuse when the session already leads another active party, or is an adventurer (see `adventurers`).
- `resolve_binding` is deterministic for databases that already hold the double binding.
- `guild drift` reports a session that leads more than one active party; `guild doctor` shows the same finding.
- Resuming the party the session already leads stays allowed.
- `README.md` and `GUILD.md` change with the code.

## Out of scope

- Moving a party's quests or PRs to another party: `guild task move` already covers tasks.
- Repairing old double bindings automatically.

## Success criteria

- [x] A test reproduces the switch, fails before the fix and passes after.
- [x] A bound session cannot become the leader of a second party from the CLI or the web.
- [x] An existing double binding shows up in `guild drift` and `guild doctor`.

## Security and data

Reads and writes only the `parties` and `leaders` projections. The refusal names the party the session leads; it carries no session id.
