---
epic: ask-context
type: tasks
title: Asks that carry the context to decide them
status: active
updated: 2026-10-04
---

# Tasks: Asks that carry the context to decide them

## T01 — Card refs

**Depends on:** —
**Status:** [ ] pending

**What:** `card:<KEY>` is a valid ask ref, validated against the cards table or the project `sdd.key_ref`; `card_url` and `pr_url` move to `guild/links.py`.

**Acceptance:**
- [ ] A known card ref is accepted and an unknown one rejected.
- [ ] A card ref satisfies the at-least-one-ref rule and never counts as blocking.

## T02 — Origin snapshot and auto-ref

**Depends on:** T01
**Status:** [ ] pending

**What:** The origin snapshot is stored in `asks.snapshot`; the single in-progress task is referenced automatically; `--ref` is optional only when that resolves.

**Acceptance:**
- [ ] The snapshot is stored, replays through `rebuild` and old asks still load.
- [ ] Auto-ref adds the single task and errors when it cannot pick one and no ref was given.

## T03 — Closed asks listing

**Depends on:** —
**Status:** [ ] pending

**What:** `asks.answered_at` from the event time and `guild asks --all [--party] [--since]`.

**Acceptance:**
- [ ] `guild asks` still lists only open asks.
- [ ] `--all` shows answered asks with answer and time; `--party` and `--since` narrow it.

## T04 — Ask detail view

**Depends on:** T01, T02, T03
**Status:** [ ] pending

**What:** `guild/ask_detail.py` expands an ask and `guild asks <id>` renders it.

**Acceptance:**
- [ ] The card link, task, spec path and resume command are shown.
- [ ] Missing refs, no snapshot and no SDD or tracker config render without errors.

## T05 — Ask detail on the web

**Depends on:** T04
**Status:** [ ] pending

**What:** `GET /api/asks/<id>` and an expandable control on the web board built with `textContent` and tooltips.

**Acceptance:**
- [ ] The endpoint returns the detail, answers 404 for an unknown ask and applies the same host checks.
- [ ] The control renders without `innerHTML`.

## T06 — Docs and spec close-out

**Depends on:** T05
**Status:** [ ] pending

**What:** README, `GUILD.md` and the spec success criteria.

**Acceptance:**
- [ ] README matches the CLI.
- [ ] `test_sdd_docs` passes.
