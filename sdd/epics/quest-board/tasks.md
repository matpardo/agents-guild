---
epic: quest-board
type: tasks
title: Prepare quests ahead for parties to take
status: done
updated: 2026-10-23
---

# Tasks: Prepare quests ahead for parties to take

## T01 — Open quest data

**Depends on:** —
**Status:** [x] done — #201

**What:** `quests.party` nullable; `quest.added` without a party is an open quest; `quest.taken` and `quest.released` events and reducers. Depends on `adventurers` T01 for adventurer-held tasks.

**Acceptance:**
- [x] A rebuild of an old event log keeps every quest's party.

## T02 — Create open quests

**Depends on:** T01
**Status:** [x] done — #201

**What:** `guild quest add --open` without a session, from a party or from an adventurer, reusing the synced-task checks and `reject_taken_tasks`.

**Acceptance:**
- [x] `--open` works with no binding; a taken task is still refused.

## T03 — Take and release

**Depends on:** T02
**Status:** [x] done — #201

**What:** `guild quest take <slug>` for the session's party and `guild quest release <slug>` for the owner while every task is queued with no open PR or claim; `take_for_party` and `release_for_owner` for the web. A task an adventurer holds stays with it.

**Acceptance:**
- [x] A party takes a quest with an adventurer-held task; the held task is skipped by `guild next` until `adventurer done`.
- [x] Release refuses a quest with a started task.

## T04 — Quest board in the CLI

**Depends on:** T01
**Status:** [x] done — #201

**What:** `guild quest board [--project <name>]` lists open quests and the synced tasks no quest covers, per epic in SDD order.

**Acceptance:**
- [x] A task in any quest or claim is never listed as free.

## T05 — Next offers open quests

**Depends on:** T03
**Status:** [x] done — #201

**What:** `guild next` answers `take open quest <slug>` to a party with no queued task, oldest open quest of its project first.

**Acceptance:**
- [x] A party with queued work is never offered an open quest.

## T06 — Quest board on the web

**Depends on:** T03, T04
**Status:** [x] done — #204

**What:** a quest board section: create an open quest from an epic's free tasks, assign to a party, release. Routes call the same command functions through `sendPost`.

**Acceptance:**
- [x] The node harness covers the section; the CLI and the web produce the same events.

## T07 — Quest board docs

**Depends on:** T03
**Status:** [x] done — #201

**What:** `README.md` command reference and a quest board section; `GUILD.md` rule to take an open quest when `guild next` offers one.

**Acceptance:**
- [x] `GUILD.md` names `quest take` and `quest add --open`.

## T08 — Quests remember who left them

**Depends on:** T03
**Status:** [x] done

**What:** `quests.left_by` holds the party or adventurer that ran `quest add --open`, or the party that released the quest. The quest board and the party block, in the CLI and the web, show it; the final report reads it instead of guessing by session.

**Acceptance:**
- [x] A session that led two parties reports each left quest only under the party that left it.
- [x] Taking a quest keeps who left it; releasing it records the releasing party.
