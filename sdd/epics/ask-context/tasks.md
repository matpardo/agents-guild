---
epic: ask-context
type: tasks
title: Asks that carry the context to decide them
status: done
updated: 2026-10-31
---

# Tasks: Asks that carry the context to decide them

## T01 — Card refs

**Depends on:** —
**Status:** [x] done — #67

**What:** `card:<KEY>` is a valid ask ref, validated against the cards table or the project `sdd.key_ref`; `card_url` and `pr_url` move to `guild/links.py`.

**Acceptance:**
- [x] A known card ref is accepted and an unknown one rejected.
- [x] A card ref satisfies the at-least-one-ref rule and never counts as blocking.

## T02 — Origin snapshot and auto-ref

**Depends on:** T01
**Status:** [x] done — #67

**What:** The origin snapshot is stored in `asks.snapshot`; the single in-progress task is referenced automatically; `--ref` is optional only when that resolves.

**Acceptance:**
- [x] The snapshot is stored, replays through `rebuild` and old asks still load.
- [x] Auto-ref adds the single task and errors when it cannot pick one and no ref was given.

## T03 — Closed asks listing

**Depends on:** —
**Status:** [x] done — #67

**What:** `asks.answered_at` from the event time and `guild asks --all [--party] [--since]`.

**Acceptance:**
- [x] `guild asks` still lists only open asks.
- [x] `--all` shows answered asks with answer and time; `--party` and `--since` narrow it.

## T04 — Ask detail view

**Depends on:** T01, T02, T03
**Status:** [x] done — #67

**What:** `guild/ask_detail.py` expands an ask and `guild asks <id>` renders it.

**Acceptance:**
- [x] The card link, task, spec path and resume command are shown.
- [x] Missing refs, no snapshot and no SDD or tracker config render without errors.

## T05 — Ask detail on the web

**Depends on:** T04
**Status:** [x] done — #67

**What:** `GET /api/asks/<id>` and an expandable control on the web board built with `textContent` and tooltips.

**Acceptance:**
- [x] The endpoint returns the detail, answers 404 for an unknown ask and applies the same host checks.
- [x] The control renders without `innerHTML`.

## T06 — Docs and spec close-out

**Depends on:** T05
**Status:** [x] done — #67

**What:** README, `GUILD.md` and the spec success criteria.

**Acceptance:**
- [x] README matches the CLI.
- [x] `test_sdd_docs` passes.

## T07 — Local times in ask views

**Depends on:** T04
**Status:** [x] done — #72

**What:** `guild asks <id>`, `guild asks --all` and the web detail show creation, answer and event times as local `YYYY-MM-DD HH:MM`; the models keep the ISO fields and add `created`, `answered` and per-event `time` labels.

## T08 — Legible asks

**Depends on:** T07
**Status:** [x] done

**What:** `guild ask` takes `--recommend` (at most 300 characters), prints a warning, without refusing, when question or context carry many ids or paths, and `--context` and `--recommend` render paragraphs, breaks and bold in the CLI and the web. `guild asks <id>` and the web detail show what decides the ask first and the paths, origin and resume command under `dig in`; the recent events and the duplicate epics and cards lines are gone.

**Acceptance:**
- [x] `--recommend` is stored, validated and shown in `guild asks`, the detail and the web card; events without it rebuild as null.
- [x] A jargon-heavy question or context prints a warning and the ask is still created.
- [x] The detail has no recent events; `dig in` is closed by default on the web.

## T09 — Multi-line answers

**Depends on:** T08
**Status:** [x] done

**What:** the answer of an ask renders paragraphs, breaks and bold like the context, in `guild asks <id>`, `guild asks --all`, `guild asks --answered`, the web detail and the web answered list.

**Acceptance:**
- [x] A multi-line answer keeps its lines in the CLI detail and lists.
- [x] The web detail and answered list build line breaks for it.

## T10 — Jargon warning false positives

**Depends on:** T08
**Status:** [x] done

**What:** the ask warning stops counting plain words (`and/or`, `cliente/servidor`) and plain numbers as ids or paths; paths with two or more slashes or a file extension, and hashes with a letter and a digit, still count.

**Acceptance:**
- [x] `and/or`, `y/o`, `cliente/servidor` and `1234567` count zero.
- [x] `a/b/c`, `guild/commands/ask.py` and `abc1234` still count one each.

## T11 — CLI bold across wraps and dim context

**Depends on:** T08
**Status:** [x] done

**What:** in the CLI, a `**bold**` span that wraps onto another line stays bold on every line, and the board dims the context, recommendation and answer text around the bold spans.

**Acceptance:**
- [x] A bold span split by a wrap is styled on both lines with its markers removed.
- [x] An unclosed `**` stays literal.
