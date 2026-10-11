---
epic: web-board
type: tasks
title: Web view of the guild board
status: done
updated: 2026-10-04
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
**Status:** [x] done — #27

**What:** `GET /api/session` serves a per-start token; `POST /api/asks/<id>/answer` and `/dismiss` require the loopback `Host` and `Origin`, the token in `X-Guild-Token`, `application/json` and a body of at most 16384 bytes, then call `ask.answer` / `ask.dismiss` as the human actor (`GuildError` becomes 422); `OPTIONS` stays 405 with no CORS headers. Each ask card gets option buttons that fill the answer field, an answer field, `Answer` and `Dismiss` (with confirmation); drafts survive the 15-second refresh.

## T06 — Status colors

**Depends on:** T03
**Status:** [x] done — #28

**What:** the page uses the terminal board's meanings through CSS classes only, with light and dark variants under `prefers-color-scheme`: a PR's lifecycle is a badge (`converging` amber, `ready` green, `draft` gray, `merged` purple, `closed` muted gray) and its human flags are badges too (`needs-ask-answer` red, `needs-human-pr-review` amber), checks show `✗N` red when N > 0 and muted otherwise, `✓N` green and `no checks` muted, and a task's state is colored (`active` blue, `blocked` red, `queued` muted). The text labels stay.

## T07 — Mark notices seen from the view

**Depends on:** T05
**Status:** [x] done — #28

**What:** a seen mark lets the human tell new notices from read ones without changing what is shown or delivered: every active notice stays listed everywhere and delivery, the brief and the notice's state are untouched. `guild notice seen <id>|--all` and `guild notice unseen <id>` (events `notice.seen` / `notice.unseen`, column `notices.seen_at`); `guild notices` and the board prefix unseen notices with `new` and count them, with time left on every notice. The web model adds `seen` per notice, `time_left` and `new_notice_count`; unseen cards get a `new` badge and `Mark seen`, seen cards `Mark unseen`, and the heading has `Mark all seen`; `POST /api/notices/<id>/seen`, `/unseen` and `POST /api/notices/seen-all` reuse the ask routes' checks.

## T08 — Notice issue time, newest first

**Depends on:** T07
**Status:** [x] done — #63

**What:** active notices are ordered newest first everywhere (`guild notices`, board, brief, handoff, web); each shows its issue time in local time (`YYYY-MM-DD HH:MM`), inbox lines read `- notice #N from X at <time>: "..."`, and the web model adds `issued_at` and `issued`.

## T09 — Tooltips on every web label

**Depends on:** T08
**Status:** [x] done — #68

**What:** every status, badge, chip and label on the page carries a `title` tooltip of one plain sentence saying what it means and, where useful, what to do: party statuses and states, PR lifecycles and human flags, check counts, task states, merge-queue states and actions, notice `new`, issue time, time left and scope, ask blocks, raid roles, drift rules, `MAIN RED`, blocked sessions and the filters. The explanations live in one frozen dictionary in `app.js`; a value with no entry gets no tooltip, and a test fails when a status the server can emit has none.

## T10 — Two-column board with collapsible notices

**Depends on:** T09
**Status:** [x] done — #74

**What:** on wide screens the board shows asks, notices, drift and resources on the left and the merge queue followed by the parties on the right; the notices section collapses and keeps its state across refreshes.

## T11 — Block or unblock a PR externally from the web

**Depends on:** T10
**Status:** [x] done — #119

**What:** the board shows a distinct `blocked: external` pill with the reason on PR cards and merge-queue entries, and the PR card has Block (asks for a reason) and Unblock actions that call `POST /api/prs/<owner>/<repo>/<n>/block` and `.../unblock`, recording the same `pr.set` event as `guild pr set --blocked-external`.
