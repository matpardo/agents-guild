---
epic: quest-bound-work
type: tasks
title: A party's work always belongs to a quest
status: done
updated: 2026-11-04
---

# Tasks: A party's work always belongs to a quest

## T01 — Party PRs need a task

**Depends on:** —
**Status:** [x] done — #205

**What:** `pr track` from a party refuses without `--task`; `--card` alone is accepted only from an adventurer with a free job. Depends on `adventurers` T04.

**Acceptance:**
- [x] A party's `pr track --card` without `--task` fails with a pointer to `task add` and `quest add --no-epic`.

## T02 — Board without new loose party PRs

**Depends on:** T01
**Status:** [x] done — #205

**What:** "PRs outside active tasks" keeps only legacy rows and PRs on queued or done tasks; adventurer PRs move to the adventurers section in the CLI and the web.

**Acceptance:**
- [x] The node harness shows an adventurer PR under the adventurer, not under a party.

## T03 — Quest-bound work docs

**Depends on:** T01
**Status:** [x] done — #205

**What:** `GUILD.md` "Track every PR" rule: a party's PR always has `--task`; loose work is an adventurer. `README.md` updated.

**Acceptance:**
- [x] No `GUILD.md` rule tells a party to use `--card` alone.

## T04 — Relink or untrack a PR

**Depends on:** T01
**Status:** [x] done

**What:** `pr set --task|--card` relinks a tracked PR and `pr untrack` drops it, in the CLI and the web board, so a merged PR that only refined a spec stops raising a card-not-done finding.

**Acceptance:**
- [x] After `pr untrack` or a relink to a task without a card, a merged PR no longer raises "card not done".

## T05 — Task add without an SDD entry

**Depends on:** T01
**Status:** [x] done

**What:** `guild task add --no-sdd` adds housekeeping work that has no entry in the epic's `tasks.md`. The flag is stored on the task, the board marks the task, and drift and the epic `quest done` gate skip it.

**Acceptance:**
- [x] A `--no-sdd` task raises no "quest task not in SDD" finding and `quest done` passes once it is done.
- [x] The flag survives `guild rebuild`.
