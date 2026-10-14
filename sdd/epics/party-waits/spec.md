---
epic: party-waits
type: spec
title: Show what each party waits on
status: active
owner: matpardo
created: 2026-10-14
updated: 2026-10-14
---

# Show what each party waits on

## Why

An idle session with pending work is a valid state. The human needs to see, per party, what the work waits on (a check, a review, a merge, an answer, a usage limit) and act on it without waking anyone. Decision `20261014_board-shows-waits-no-dispatcher` retires the dispatcher, keeper parties and the raid lead role; this epic replaces the signals the dispatcher gave.

## What

- `guild/party_waits.py` computes a list of waits per party from the projections: `checks-pending`, `checks-failing`, `conflict`, `behind`, `changes-requested`, `threads`, `human-review`, `human-merge`, `draft-green`, `fix-requested`, `ask-open`, `ask-answered-unseen`, `notices-unread`, `limit-reset`.
- `guild board` prints a `waits on:` line per party and the web board one pill per wait, both fed by the `waits` key of the party model.
- Closed parties have no waits.
