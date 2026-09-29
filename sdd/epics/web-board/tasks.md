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
**Status:** [x] done

**What:** `board_model(ctx)` in `guild/commands/board.py` returns the board as plain dicts/lists (asks with blocked counts, notices, parties with quests, tasks, PRs, raids and claims, and default-scope drift findings per project), reusing the existing queries (extracted into small helpers shared with the terminal renderer, which is unchanged). The JSON endpoint serves it.

## T02 — guild web server

**Depends on:** T01
**Status:** [x] done

**What:** `guild web --port <n>` (`guild/webserver.py`, `ThreadingHTTPServer` on 127.0.0.1, `--port 0` lets the OS pick, prints the real URL); routes `/` (page), `/app.js`, `/app.css`, `/api/board`; `Host` check (421), CSP/`nosniff`/`Referrer-Policy` headers on every response, `Cache-Control: no-store` on `/api/*`, 404 and 405; quiet access log, Ctrl-C exits 0.

## T03 — Page

**Depends on:** T02
**Status:** [ ] pending

**What:** asks first, notices, party blocks with PRs under tasks; filters by party and state; collapsible blocks; refresh every 15 seconds; all text via `textContent`.

## T04 — Links to PRs and cards

**Depends on:** T03
**Status:** [ ] pending

**What:** PR links to GitHub; card links built from an optional explicit `tracker.browse_url` in the project config (no link when absent).
