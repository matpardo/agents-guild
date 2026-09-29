---
epic: web-board
type: tasks
title: Web view of the guild board
status: done
updated: 2026-09-29
---

# Tasks: Web view of the guild board

## T01 — Board data model

**Depends on:** —
**Status:** [x] done — #14

**What:** `board_model(ctx)` in `guild/commands/board.py` returns the board as plain dicts/lists (asks with blocked counts, notices, parties with quests, tasks, PRs, raids and claims, and default-scope drift findings per project), reusing the existing queries (extracted into small helpers shared with the terminal renderer, which is unchanged). The JSON endpoint serves it.

## T02 — guild web server

**Depends on:** T01
**Status:** [x] done — #14

**What:** `guild web --port <n>` (`guild/webserver.py`, `ThreadingHTTPServer` on 127.0.0.1, `--port 0` lets the OS pick, prints the real URL); routes `/` (page), `/app.js`, `/app.css`, `/api/board`; `Host` check (421), CSP/`nosniff`/`Referrer-Policy` headers on every response, `Cache-Control: no-store` on `/api/*`, 404 and 405; quiet access log, Ctrl-C exits 0.

## T03 — Page

**Depends on:** T02
**Status:** [x] done — #14

**What:** `guild/web/index.html`, `app.js`, `app.css`: asks first (question, party, options, refs, blocks count, collapsible context), then notices, then drift findings, then one collapsible block per party with quests → tasks → PRs; a party filter and a state filter that apply to PRs; refresh every 15 seconds keeping filter and collapse state; every node built with `document.createElement`/`textContent`, never HTML injection; light/dark via `prefers-color-scheme`, responsive to phone width, no external fonts.

## T04 — Links to PRs and cards

**Depends on:** T03
**Status:** [x] done — #14

**What:** PR `url` (`https://github.com/<repo>/pull/<n>`) and a task's `card_url` render as `<a target="_blank" rel="noopener noreferrer">` links; `card_url` is present only when the task has a tracker key and the project configures `tracker.browse_url` (`browse_url + key`). `tracker.browse_url` is validated when the project config is loaded — it must start with `https://`, otherwise a clear error — and documented in the README's "Project config" section.

## T05 — Answer and dismiss asks from the page

**Depends on:** T03
**Status:** [x] done

**What:** `GET /api/session` serves a per-start token; `POST /api/asks/<id>/answer` and `/dismiss` require the loopback `Host` and `Origin`, the token in `X-Guild-Token`, `application/json` and a body of at most 16384 bytes, then call `ask.answer` / `ask.dismiss` as the human actor (`GuildError` becomes 422); `OPTIONS` stays 405 with no CORS headers. Each ask card gets option buttons that fill the answer field, an answer field, `Answer` and `Dismiss` (with confirmation); drafts survive the 15-second refresh.
