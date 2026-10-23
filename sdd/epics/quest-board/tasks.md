---
epic: quest-board
type: tasks
title: Prepare quests ahead for parties to take
status: draft
updated: 2026-10-23
---

# Tasks: Prepare quests ahead for parties to take

## T01 — Open quest data

**Depends on:** —
**Status:** [ ] pending

**What:** `quests.party` nullable; `quest.added` without a party is an open quest; `quest.taken` and `quest.released` events and reducers. Depends on `adventurers` T01 for adventurer-held tasks.

**Acceptance:**
- [ ] A rebuild of an old event log keeps every quest's party.

## T02 — Create open quests

**Depends on:** T01
**Status:** [ ] pending

**What:** `guild quest add --open` without a session, from a party or from an adventurer, reusing the synced-task checks and `reject_taken_tasks`.

**Acceptance:**
- [ ] `--open` works with no binding; a taken task is still refused.

## T03 — Take and release

**Depends on:** T02
**Status:** [ ] pending

**What:** `guild quest take <slug>` for the session's party and `guild quest release <slug>` for the owner while no task started. A task an adventurer holds stays with it.

**Acceptance:**
- [ ] A party takes a quest with an adventurer-held task; the held task is skipped by `guild next` until `adventurer done`.
- [ ] Release refuses a quest with a started task.

## T04 — Quest board in the CLI

**Depends on:** T01
**Status:** [ ] pending

**What:** `guild quest board [--project <name>]` lists open quests and the synced tasks no quest covers, per epic in SDD order.

**Acceptance:**
- [ ] A task in any quest or claim is never listed as free.

## T05 — Next offers open quests

**Depends on:** T03
**Status:** [ ] pending

**What:** `guild next` answers `take open quest <slug>` to a party with no queued task, oldest open quest of its project first.

**Acceptance:**
- [ ] A party with queued work is never offered an open quest.

## T06 — Quest board on the web

**Depends on:** T03, T04
**Status:** [ ] pending

**What:** a quest board section: create an open quest from an epic's free tasks, assign to a party, release. Routes call the same command functions through `sendPost`.

**Acceptance:**
- [ ] The node harness covers the section; the CLI and the web produce the same events.

## T07 — Quest board docs

**Depends on:** T03
**Status:** [ ] pending

**What:** `README.md` command reference and a quest board section; `GUILD.md` rule to take an open quest when `guild next` offers one.

**Acceptance:**
- [ ] `GUILD.md` names `quest take` and `quest add --open`.
