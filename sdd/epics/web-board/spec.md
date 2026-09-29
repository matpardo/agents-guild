---
epic: web-board
type: spec
title: Web view of the guild board
status: active
owner: matpardo
created: 2026-09-28
updated: 2026-09-28
---

# Spec: Web view of the guild board

## Goal

See the guild board, asks and notices in a browser, with a clearer layout than the terminal allows.

## Problem

`guild board` is readable but dense: many parties, PRs and asks compete for one terminal screen, and there is no way to filter, collapse or link out to PRs and cards.

## Scope

- `guild web --port <n>`: a local server from the Python standard library, bound to 127.0.0.1 only, reading guild's own database. No dependencies, no build step.
- One HTML page with plain JavaScript, fed by a JSON endpoint: asks first (ordered by what they still block), then notices, then one block per party with quests, tasks and PRs nested under their tasks; raids and claims per party; drift findings for work in progress.
- Filters by party and by state; collapsible party blocks; periodic refresh.
- Links to PRs on GitHub and, when configured, to cards in the tracker.

## Out of scope

- Writing from the page (answering asks). A later task, with its own security design.
- Other machines (see `federation`).
- Replacing the terminal board.

## Success criteria

- [ ] A human finds every open ask and its context without opening a terminal.
- [ ] The page never executes text coming from agents, SDD, GitHub or the tracker.

## Security and data

- Bound to 127.0.0.1; requests whose `Host` header is not the loopback address and port are rejected (blocks DNS rebinding).
- Read-only: only `GET`; anything else is 405.
- All text is inserted with `textContent`, never as HTML. A strict `Content-Security-Policy` (`default-src 'self'`) forbids inline and third-party scripts; no external assets.
- The JSON carries the same free text as the terminal board; it never leaves the machine.
