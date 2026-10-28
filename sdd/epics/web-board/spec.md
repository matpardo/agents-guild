---
epic: web-board
type: spec
title: Web view of the guild board
status: done
owner: matpardo
created: 2026-09-28
updated: 2026-10-04
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
- Writing from the page: answering and dismissing open asks, with the same validation as `guild answer` and `guild dismiss`, acting as the human actor.
- Status colors, matching the terminal board: PR lifecycle badges, check counts and task states, light and dark.
- Marking notices seen from the human's view: a `new` marker on unseen notices in `guild notices`, the board and the web page, with buttons to mark one or all seen, without changing what is shown or delivered.
- Notices carry their issue time and are listed newest first, in the terminal, the inbox and the web page.
- Every status, badge and label on the page explains itself with a tooltip.

## Out of scope

- Writing anything from the page other than answering and dismissing asks and marking notices seen or unseen.
- Other machines (see `federation`).
- Replacing the terminal board.

## Success criteria

- [x] A human finds every open ask and its context without opening a terminal.
- [x] The page never executes text coming from agents, SDD, GitHub or the tracker.

## Security and data

- Bound to 127.0.0.1; requests whose `Host` header is not the loopback address and port are rejected (blocks DNS rebinding).
- Writes are limited to `POST /api/asks/<id>/answer`, `POST /api/asks/<id>/dismiss`, `POST /api/notices/<id>/seen`, `POST /api/notices/<id>/unseen` and `POST /api/notices/seen-all`; every other method, including `OPTIONS`, is 405, and no response carries CORS headers.
- Each write must carry an `Origin` equal to the loopback address and port (403), a per-start session token in `X-Guild-Token` compared in constant time (403), `Content-Type: application/json` (415), a `Content-Length` of at most 16384 bytes (411/413) and a valid JSON object (400).
- The session token comes from `secrets.token_urlsafe(32)`, lives in memory only, is never logged, and is handed to the browser only in the URL fragment `guild web` prints (`#t=<token>`); the page keeps it in `sessionStorage` for its tab, strips it from the address bar and sends it on every `/api` request; every `/api` GET without it is 403.
- Notice writes reuse `guild notice seen` / `unseen` as the human actor and go through the same header, token and body checks as the ask writes.
- Writes reuse `guild answer` / `guild dismiss` (length cap, email and `pii_patterns` rejection, "not open", unknown ask) as the human actor; failures are 422 with a message that never echoes the submitted text.
- All text is inserted with `textContent`, never as HTML. A strict `Content-Security-Policy` (`default-src 'self'`) forbids inline and third-party scripts; no external assets.
- The JSON carries the same free text as the terminal board; it never leaves the machine.
