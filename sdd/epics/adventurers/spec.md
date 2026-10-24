---
epic: adventurers
type: spec
title: Adventurers do one job and report what is pending
status: done
owner: matpardo
created: 2026-10-23
updated: 2026-10-24
---

# Spec: Adventurers do one job and report what is pending

## Goal

Every session that works on a registered project is visible on the board, and every session that stops leaves a record of what is pending.

## Problem

Sessions outside a party leave no trace in guild: the human cannot see what they did, which PRs they opened or what they left half done. Parties record pending work through `guild handoff`, but a party whose leader dies without one leaves nothing. One-off work either hides or gets wrapped in a party it does not need.

## Scope

- An adventurer is one session, one project and one job. The job is free text; it may be tied to one synced SDD task (`<epic>/<tid>`). Tasks of open quests come with `quest-board`.
- `guild adventurer start "<job>" [--task <epic>/<tid>]` registers the session; the project comes from the cwd. The adventurer row holds the task, not a claim: `adventurer start` refuses an unknown task, a task in an active quest, a task under a live `task:<epic>/<tid>` claim and a task another active adventurer holds; `quest add`, `task add`, `claim` and `claim check` treat a task held by an active adventurer as taken.
- `guild adventurer done --pending "<text>"` ends it; `--pending none` is the explicit empty report. The text passes the same checks as `--learned`.
- `guild adventurers [id]` lists them; the web shows the same.
- An adventurer may track its PRs (`--task <its task>` or `--card`; the PR records the adventurer), post notices, add ideas and open asks, and creates open quests once `quest-board` lands. It never takes or owns a quest, adds tasks or changes a task: its task is done when SDD says so. Any command that needs a party refuses it with "adventurers do one job; quests and tasks belong to parties".
- A session is a party leader, an adventurer or unbound: `party start` and `party resume` refuse an active adventurer; `adventurer start` refuses a leader.
- The Stop hook records `session.stopped` for adventurers too.
- The board and the web list adventurers with job, live or stopped, PRs and pending report, and flag one that stopped without reporting. A done adventurer stays listed until `guild adventurer dismiss <id>` (web: Dismiss button). A party whose leader is gone without a handoff gets the same flag.
- `guild party close` and `guild adventurer done` print a final report block (PRs with state, quests with done/total tasks, linked ideas, pending) read from existing state; the session ends with a report to the human built from it (decisión del dev, 2026-10-23).
- `guild party close` requires `--pending`, validated like `--learned` and stored on the `party.closed` event.
- The unbound hint tells the session to choose party or adventurer itself, with a reason, before any work that changes a repo of a registered project; it asks the human only when unsure (T10).
- `README.md` and `GUILD.md` change with the code.

## Out of scope

- A Stop hook that blocks until the session reports (dropped in `20261012_dispatcher-suggests-human-launches`).
- Inferring pending work from transcripts.
- Turning an adventurer into a party was out of scope here; `adventurer promote` covers it (T10).

## Success criteria

- [x] An adventurer appears on the CLI and web board from `adventurer start` until it is dismissed.
- [x] A stopped adventurer with no report, and a gone leader with no handoff, are flagged.
- [x] An adventurer cannot take a quest or change a task that is not its own.
- [x] Adventurer state survives `guild rebuild`.

## Security and data

Adventurers are local events. Job and pending text go through the email, secret and project-pattern checks of other fields and never leave the CLI. Web writes need the session token like every other write. An adventurer holds its task until `adventurer done`.
