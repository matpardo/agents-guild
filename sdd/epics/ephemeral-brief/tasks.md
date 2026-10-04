---
epic: ephemeral-brief
type: tasks
title: Short sessions started from a task brief
status: active
updated: 2026-10-04
---

# Tasks: Short sessions started from a task brief

## T01 — Shared task context helpers

**Depends on:** —
**Status:** [ ] pending

**What:** `guild/task_context.py` holds the project config, SDD path and task reference helpers that `ask_detail` used privately; `ask_detail` imports them and its output does not change.

**Acceptance:**
- [ ] `guild asks <id>` output is unchanged.
- [ ] Task, missing task and SDD paths (root and git_ref) resolve as before.

## T02 — Idle and queued party status

**Depends on:** —
**Status:** [ ] pending

**What:** the derived party status checks for a live leader session first; a party without one shows `waiting-ask`, `queued` (work waiting) or `idle`, and `unknown` is kept for a live session that never reported. `awaiting-leader` stays a stored party state and stops being a display status.

**Acceptance:**
- [ ] A handed-off party with work shows `queued`, without work `idle`.
- [ ] A dead session with a stale `working` row shows `idle` or `queued`.
- [ ] A live session that never reported still shows `unknown`.
- [ ] `awaiting-leader` is never a display status.

## T03 — `guild brief <party>/<quest>/<tid>`

**Depends on:** T01
**Status:** [ ] pending

**What:** `guild brief` takes an optional task reference and prints a read-only brief of at most 4000 characters: task, PRs with review comment counts, related asks, targeted notices, claims and the last handoff.

**Acceptance:**
- [ ] `guild brief` without an argument is unchanged.
- [ ] The output is at most 4000 characters and says what was cut.
- [ ] Dynamic text is stripped of control sequences and single-lined.
- [ ] Unknown party, closed party, foreign quest and unknown task fail clearly and write nothing.

## T04 — Fresh sessions start from the brief

**Depends on:** T03
**Status:** [ ] pending

**What:** the `SessionStart` hook of a resumed generation injects the task brief followed by the `guild next` line, once per generation; the fixed resume prompt points at the brief.

**Acceptance:**
- [ ] A fresh generation sees handoff, task, PRs, asks and notices before its first prompt, once per generation.
- [ ] A party with no task still gets the handoff and the `guild next` line.
- [ ] Reading the brief acknowledges nothing and writes no event.

## T05 — Vocabulary amendment

**Depends on:** T02
**Status:** [ ] pending

**What:** a new decision supersedes the vocabulary decision with leader as the live session (zero or one), generation, keeper, raid lead and brief.

**Acceptance:**
- [ ] The old decision points at the new one.
- [ ] The README glossary and status list match.

## T06 — Docs and spec

**Depends on:** T03, T04, T05
**Status:** [ ] pending

**What:** README syntax list, task brief section, hook description and project config recommend threshold 40; `GUILD.md` says sessions are short and the brief is injected; the spec is marked active.

**Acceptance:**
- [ ] The README syntax list, hook description and project config mention the brief and threshold 40.
- [ ] `GUILD.md` says sessions are short and the brief is injected.
