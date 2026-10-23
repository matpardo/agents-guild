---
epic: adventurers
type: tasks
title: Adventurers do one job and report what is pending
status: active
updated: 2026-10-23
---

# Tasks: Adventurers do one job and report what is pending

## T01 — Adventurer data

**Depends on:** —
**Status:** [x] done — #199

**What:** `adventurers` table, `adventurer.started` and `adventurer.done` events and their reducers; the row holds the SDD task (`<epic>/<tid>`) the adventurer works on; `prs.adventurer` column.

**Acceptance:**
- [x] Adventurers and the task they hold survive `guild rebuild`.

## T02 — Adventurer commands

**Depends on:** T01
**Status:** [x] done — #199

**What:** `guild adventurer start "<job>" [--task <epic>/<tid>]`, `guild adventurer done --pending "<text>"` and `guild adventurers [id]`. `start` refuses a session that leads a party (see `party-identity` T01), an unknown task, a task in an active quest, a task under a live claim and a task another adventurer holds; `party start` and `party resume` refuse an active adventurer.

**Acceptance:**
- [x] `done` without `--pending` fails; `--pending none` is accepted.
- [x] A task held by an adventurer is refused by `quest add`, `task add`, `claim` and `claim check` of every party.

## T03 — Hooks and the party-or-adventurer question

**Depends on:** T01
**Status:** [x] done — #199

**What:** the Stop hook records `session.stopped` for adventurers; the unbound hint asks the session to ask the human "party or adventurer" before working on a registered project.

**Acceptance:**
- [x] An adventurer's stop is recorded; an unbound session in a registered project sees the question once.

## T04 — What an adventurer may do

**Depends on:** T02
**Status:** [x] done — #199

**What:** `pr track` (with `--card` or its own `--task`), `notice`, `idea` and `ask` accept an adventurer and label it `adventurer <id>`; every command that needs a party (`require_binding`) refuses it with "adventurers do one job; quests and tasks belong to parties". `quest add --open` comes with `quest-board`.

**Acceptance:**
- [x] Each allowed and refused command has a test.

## T05 — Adventurers and missing reports on the board

**Depends on:** T02
**Status:** [ ] pending

**What:** an adventurers section in `guild board` and the web with job, live or stopped, PRs and pending report; a `stopped without report` flag for adventurers and for parties whose leader is gone without a handoff; `guild party close` requires `--pending`. Web writes go through `sendPost` and the same command functions.

**Acceptance:**
- [ ] The node harness covers the section and the flag.
- [ ] `party close` without `--pending` fails from the CLI and the web.

## T06 — Adventurer docs

**Depends on:** T04
**Status:** [ ] pending

**What:** `GUILD.md` rules: ask party or adventurer first, and every session that stops reports what is pending. `README.md` command reference. The first PR already ships the adventurer rules and commands; this task closes what is left.

**Acceptance:**
- [ ] `tests/test_no_traces.py` covers adventurer ids and pending text.
