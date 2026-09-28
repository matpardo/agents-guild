---
epic: core-cli
type: spec
title: Core CLI for coordinating parallel sessions
status: done
owner: matpardo
created: 2026-09-27
updated: 2026-09-28
---

# Spec: Core CLI for coordinating parallel sessions

## Goal

Give parallel Claude Code sessions one deterministic place to register their work, ask the human for decisions, and warn each other.

## Problem

Each session sees only its own context. A finding (a CI outage and its fix) does not travel; nobody knows what is in flight or which decisions wait on the human; sessions keep stale PR state (a commit pushed to an already merged PR); decisions get lost across messages.

## Scope

- Parties bound to sessions, quests, tasks, tracked PRs reconciled against `gh`.
- Human decision queue (`ask`, `answer`, `dismiss`), notices with TTL and merge conditions, area claims.
- Hooks: session start brief, per-prompt inbox, pre-push guard against merged branches.
- Human views (`board`, `asks`) and agent rules shipped as an importable `GUILD.md`.

## Out of scope

- Reading SDD or tracker data (see `keep-moving`, `three-way-tracking`).
- Anything across machines.

## Success criteria

- [x] A notice created in one session appears once in another session's next prompt.
- [x] An answer typed in a plain terminal reaches the asking session.
- [x] Pushing to a branch whose PR is merged is blocked.
- [x] `guild rebuild` reproduces identical projections.

## Security and data

Local, single-user. Free text is broadcast to every session; hardened in `security-hardening`.

## Known limitations

- Every plain terminal is the same actor `human`.
- Seeded parties show as active without a session until resumed.
