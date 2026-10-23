---
epic: adventurers
type: tasks
title: Adventurers do one job and report what is pending
status: draft
updated: 2026-10-23
---

# Tasks: Adventurers do one job and report what is pending

## T01 — Adventurer data

**Depends on:** —
**Status:** [ ] pending

**What:** `adventurers` table, `adventurer.started` and `adventurer.done` events and their reducers; claims can be held by an adventurer as well as a party.

**Acceptance:**
- [ ] Adventurers and their claims survive `guild rebuild`.

## T02 — Adventurer commands

**Depends on:** T01
**Status:** [ ] pending

**What:** `guild adventurer start "<job>" [--task <ref>]`, `guild adventurer done --pending "<text>"` and `guild adventurers [id]`. `start` refuses a session that leads a party (see `party-identity` T01) or a task another party or adventurer holds.

**Acceptance:**
- [ ] `done` without `--pending` fails; `--pending none` is accepted.
- [ ] A task taken by an adventurer is skipped by `quest add`, `claim check` and `guild next` of every party.

## T03 — Hooks and the party-or-adventurer question

**Depends on:** T01
**Status:** [ ] pending

**What:** the Stop hook records `session.stopped` for adventurers; the unbound hint asks the session to ask the human "party or adventurer" before working on a registered project.

**Acceptance:**
- [ ] An adventurer's stop is recorded; an unbound session in a registered project sees the question once.

## T04 — What an adventurer may do

**Depends on:** T02
**Status:** [ ] pending

**What:** `pr track`, `task done`, `notice`, `idea`, `ask` and `quest add --open` accept an adventurer; `quest take`, `quest add` for itself, `task add` and any change to another task refuse it.

**Acceptance:**
- [ ] Each allowed and refused command has a test.

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

**What:** `GUILD.md` rules: ask party or adventurer first, and every session that stops reports what is pending. `README.md` command reference.

**Acceptance:**
- [ ] `tests/test_no_traces.py` covers adventurer ids and pending text.
