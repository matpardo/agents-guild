---
epic: ideas
type: tasks
title: Ideas backlog
status: done
updated: 2026-10-21
---

# Tasks: Ideas backlog

## T01 — Ideas data, commands and CLI

**Depends on:** —
**Status:** [x] done — #189

**What:** `ideas` table, `idea.created`, `idea.edited` and `idea.deleted` events, `guild idea add|edit|delete` and `guild ideas [id]`.

**Acceptance:**
- [x] Ideas sort by deadline, no deadline last, overdue marked, and survive `guild rebuild`.

## T02 — Ideas on the web board

**Depends on:** T01
**Status:** [x] done — #189

**What:** `ideas` in the board model, the `POST /api/ideas/*` routes and an ideas section with form, inline edit and delete.

**Acceptance:**
- [x] The web creates, edits and deletes ideas and shows the overdue ones.

## T03 — Ideas docs and agent rule

**Depends on:** T01
**Status:** [x] done — #189

**What:** `README.md` command reference and Ideas section, one `GUILD.md` rule, and the trace guard covering idea ids.

**Acceptance:**
- [x] `GUILD.md` tells agents to delete an idea once it is turned into work.

## T04 — Idea form inputs

**Depends on:** T02
**Status:** [x] done — #190

**What:** The web deadline is typed as `YYYY-MM-DD` and the project select lists every registered project.

**Acceptance:**
- [x] The deadline input is a text field asking for `YYYY-MM-DD`, and the select lists all registered projects with a `no project` choice.
