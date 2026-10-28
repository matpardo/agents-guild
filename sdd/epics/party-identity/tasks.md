---
epic: party-identity
type: tasks
title: A session leads one party for its whole life
status: done
updated: 2026-10-28
---

# Tasks: A session leads one party for its whole life

## T01 — Refuse a second party for a bound session

**Depends on:** —
**Status:** [x] done — #198

**What:** `party start` and `party resume` check the session's current binding first and raise a `GuildError` naming the party it leads. A failing test reproduces the switch before the fix.

**Acceptance:**
- [x] A session that leads party A cannot start or resume party B.
- [x] Resuming party A from its own leader session still succeeds.

## T02 — Deterministic binding and a drift finding

**Depends on:** T01
**Status:** [x] done — #198

**What:** `resolve_binding` picks the most recent `party.started` or `party.resumed` of the session. A drift rule and a `guild doctor` check report a session that leads more than one active party.

**Acceptance:**
- [x] A rebuilt database with a double binding resolves the same party every time and shows one drift finding.

## T03 — Identity docs

**Depends on:** T01
**Status:** [x] done — #198

**What:** `GUILD.md` says a session never switches party; `README.md` documents the refusal and the finding.

**Acceptance:**
- [x] `GUILD.md` names the rule next to the binding rule.

## T04 — A party name is never reused

**Depends on:** T01
**Status:** [x] done

**What:** tests guard that `party start` and `adventurer promote` refuse the name of a closed party, and `README.md` says a name always means one party and its history.

**Acceptance:**
- [x] Starting or promoting onto a closed party's name fails with `already exists`.
