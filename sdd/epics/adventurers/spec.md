---
epic: adventurers
type: spec
title: Adventurers do one job and report what is pending
status: draft
owner: matpardo
created: 2026-10-23
updated: 2026-10-23
---

# Spec: Adventurers do one job and report what is pending

## Goal

Every session that works on a registered project is visible on the board, and every session that stops leaves a record of what is pending.

## Problem

Sessions outside a party leave no trace in guild: the human cannot see what they did, which PRs they opened or what they left half done. Parties record pending work through `guild handoff`, but a party whose leader dies without one leaves nothing. One-off work either hides or gets wrapped in a party it does not need.

## Scope

- An adventurer is one session, one project and one job. The job is free text, one task of an open quest (`<quest>/<tid>`) or one synced SDD task (`<epic>/<tid>`).
- `guild adventurer start "<job>" [--task <ref>]` registers the session; the project comes from the cwd. A task is claimed for the adventurer with the claims guild already has, so `quest add`, `quest take`, `claim check` and `guild next` skip it.
- `guild adventurer done --pending "<text>"` ends it; `--pending none` is the explicit empty report. The text passes the same checks as `--learned`.
- `guild adventurers [id]` lists them; the web shows the same.
- An adventurer may track its PRs (`--task <its task>` or `--card`), mark its own task done, post notices, add ideas, open asks and create open quests (see `quest-board`). It never takes or owns a quest, adds tasks or changes another task.
- The Stop hook records `session.stopped` for adventurers too.
- The board and the web list adventurers with job, live or stopped, PRs and pending report, and flag one that stopped without reporting. A party whose leader is gone without a handoff gets the same flag.
- `guild party close` requires `--pending`.
- The unbound hint tells the session to ask the human, before any work on a registered project, whether it is a party or an adventurer.
- `README.md` and `GUILD.md` change with the code.

## Out of scope

- A Stop hook that blocks until the session reports (dropped in `20261012_dispatcher-suggests-human-launches`).
- Inferring pending work from transcripts.
- Turning an adventurer into a party: it reports and a new party session starts.

## Success criteria

- [ ] An adventurer appears on the CLI and web board from `adventurer start` until it is dismissed.
- [ ] A stopped adventurer with no report, and a gone leader with no handoff, are flagged.
- [ ] An adventurer cannot take a quest or change a task that is not its own.
- [ ] Adventurer state survives `guild rebuild`.

## Security and data

Adventurers are local events. Job and pending text go through the email, secret and project-pattern checks of other fields and never leave the CLI. Web writes need the session token like every other write. An adventurer's claims expire like any claim.
