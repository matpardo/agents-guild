---
epic: ideas
type: tasks
title: Ideas backlog
status: done
updated: 2026-10-23
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

## T05 — Link ideas to parties

**Depends on:** T01
**Status:** [x] done — #203

**What:** `guild idea link|unlink` and `POST /api/ideas/<id>/link|unlink` tie an idea to the parties working on it; `guild ideas`, `guild board` and the web show both sides, and `GUILD.md` tells a party to link the idea it starts from.

**Acceptance:**
- [x] A session links and unlinks its own party; the human terminal passes `--party`; unknown or closed parties, unknown ideas and double links are refused.
- [x] `guild ideas` shows `worked by:` and the party block in `guild board` lists its ideas, and the links survive `guild rebuild` and vanish with the idea.
- [x] The web links and unlinks through the same functions as the CLI.
