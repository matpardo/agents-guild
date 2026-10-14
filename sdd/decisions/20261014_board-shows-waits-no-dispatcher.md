# ADR: The board shows what each party waits on; the dispatcher retires

- **Date:** 2026-10-14
- **Status:** accepted
- **Supersedes:** 20261012_dispatcher-suggests-human-launches

## Context

The dispatcher watched events and, for a party that stopped, posted a suggestion for the human to run `guild revive`. It needs rules, deferral state, a timer and notifications, and it still leaves the human guessing what a quiet party waits on. A session that is idle with pending work is a normal state: the work waits on a check, a review, a merge, an answer or a usage limit, not on guild to wake anyone.

## Decision

Decisión del dev, 2026-10-14: the board shows what each party's work waits on, computed on read from the projections. Every party block of `guild board` and the web board lists its waits (checks pending or failing, conflict, behind, changes requested, unresolved threads, human review, human merge, green draft, fix requested, open ask, answered ask not yet read, unread notices, usage limit reset), so the human acts without waking anyone. The dispatcher, keeper parties and the raid lead role retire in follow-up changes.

## Consequences

Nothing is suggested or launched on a timer. The predicates the dispatcher rules used move to `guild/party_waits.py` so the dispatcher can be deleted without losing them. Until the follow-up changes land, the dispatcher keeps working as before.

## Revisit when

- Parties stay idle with work nobody sees on the board, so a push signal is needed again.
