---
epic: keep-moving
type: tasks
title: Keep work moving without the human
status: done
updated: 2026-09-28
---

# Tasks: Keep work moving without the human

## T01 — Schema migration for observed epics and tasks

**Depends on:** —
**Status:** [x] done — #1

**What:** idempotent column migrations; `epics`, `tasks` tables; legacy events tolerated.

## T02 — SDD adapter and sync

**Depends on:** T01
**Status:** [x] done — #1

**What:** pure parser with three explicit regexes; unparseable files reported, others continue.

## T03 — Done-ness resolver

**Depends on:** T02
**Status:** [x] done — #1

**What:** guild > tracker > SDD; unknown means not done; disagreements returned.

## T04 — guild next

**Depends on:** T03
**Status:** [x] done — #1

**What:** five tiers; task claims respected; `--all` read-only.

## T05 — Handoff and resume

**Depends on:** T04
**Status:** [x] done — #1

**What:** context nudge, `guild handoff`, resume prints handoff and next item; `--session` from a terminal.

## T06 — PostToolUse hook

**Depends on:** —
**Status:** [x] done — #1

**What:** JSON `additionalContext`, shared cursor with prompt-submit.

## T07 — Title regex takes the first separator

**Depends on:** T02
**Status:** [x] done — #2

**What:** hyphens inside titles were cutting them; match lazily up to the first spaced dash.

## T08 — Next session binds itself on handoff

**Depends on:** T05
**Status:** [x] done

**What:** the printed resume command put backticks inside double quotes, so the human's shell ran `guild party resume` before `claude` started and the prompt arrived empty. The command is now `GUILD_RESUME=<party> claude -n <party>-g<N+1> '<fixed prompt>'`; the `SessionStart` hook binds an `awaiting-leader` party and injects the handoff, so the agent runs nothing.
