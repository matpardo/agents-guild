---
epic: web-board
type: tasks
title: Web view of the guild board
status: active
updated: 2026-09-28
---

# Tasks: Web view of the guild board

## T01 — Board data model

**Depends on:** —
**Status:** [ ] pending

**What:** one function that returns the board as plain data (asks with blocked counts, notices, parties with quests, tasks, PRs, raids and claims, and default-scope drift findings), reusing the existing queries. The JSON endpoint serves it.

## T02 — guild web server

**Depends on:** T01
**Status:** [ ] pending

**What:** `guild web --port <n>` on 127.0.0.1; routes `/` (page), `/app.js`, `/app.css`, `/api/board`; `Host` check, CSP and `nosniff` headers, 404 and 405.

## T03 — Page

**Depends on:** T02
**Status:** [ ] pending

**What:** asks first, notices, party blocks with PRs under tasks; filters by party and state; collapsible blocks; refresh every 15 seconds; all text via `textContent`.

## T04 — Links to PRs and cards

**Depends on:** T03
**Status:** [ ] pending

**What:** PR links to GitHub; card links built from an optional explicit `tracker.browse_url` in the project config (no link when absent).
