---
epic: party-identity
type: tasks
title: A session leads one party for its whole life
status: draft
updated: 2026-10-23
---

# Tasks: A session leads one party for its whole life

## T01 — Refuse a second party for a bound session

**Depends on:** —
**Status:** [ ] pending

**What:** `party start` and `party resume` check the session's current binding first and raise a `GuildError` naming the party it leads. A failing test reproduces the switch before the fix.

**Acceptance:**
- [ ] A session that leads party A cannot start or resume party B.
- [ ] Resuming party A from its own leader session still succeeds.

## T02 — Deterministic binding and a drift finding

**Depends on:** T01
**Status:** [ ] pending

**What:** `resolve_binding` picks the most recent `party.started` or `party.resumed` of the session. A drift rule and a `guild doctor` check report a session that leads more than one active party.

**Acceptance:**
- [ ] A rebuilt database with a double binding resolves the same party every time and shows one drift finding.

## T03 — Identity docs

**Depends on:** T01
**Status:** [ ] pending

**What:** `GUILD.md` says a session never switches party; `README.md` documents the refusal and the finding.

**Acceptance:**
- [ ] `GUILD.md` names the rule next to the binding rule.
