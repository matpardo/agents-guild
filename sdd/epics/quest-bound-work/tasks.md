---
epic: quest-bound-work
type: tasks
title: A party's work always belongs to a quest
status: draft
updated: 2026-10-23
---

# Tasks: A party's work always belongs to a quest

## T01 — Party PRs need a task

**Depends on:** —
**Status:** [ ] pending

**What:** `pr track` from a party refuses without `--task`; `--card` alone is accepted only from an adventurer with a free job. Depends on `adventurers` T04.

**Acceptance:**
- [ ] A party's `pr track --card` without `--task` fails with a pointer to `task add` and `quest add --no-epic`.

## T02 — Board without new loose party PRs

**Depends on:** T01
**Status:** [ ] pending

**What:** "PRs outside active tasks" keeps only legacy rows and PRs on queued or done tasks; adventurer PRs move to the adventurers section in the CLI and the web.

**Acceptance:**
- [ ] The node harness shows an adventurer PR under the adventurer, not under a party.

## T03 — Quest-bound work docs

**Depends on:** T01
**Status:** [ ] pending

**What:** `GUILD.md` "Track every PR" rule: a party's PR always has `--task`; loose work is an adventurer. `README.md` updated.

**Acceptance:**
- [ ] No `GUILD.md` rule tells a party to use `--card` alone.
