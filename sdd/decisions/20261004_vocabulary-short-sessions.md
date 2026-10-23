# ADR: Vocabulary for short sessions (leader, generation, keeper, raid lead, brief)

- **Date:** 2026-10-04
- **Status:** superseded by 20261023_adventurers-and-open-quests

## Context

Decision `20260927_vocabulary` described a leader as the current session of a party. With short sessions a party without a live session is the normal state, not an anomaly, and the system now persists and routes on a few more things (generations, keepers, raid leads, the brief).

## Decision

| Term | Meaning |
|---|---|
| guild | one install: database and config |
| party | durable work lineage that survives handoffs; owns quests, PRs, claims |
| leader | the live session of a party: zero or one (attribute, no commands) |
| generation | one session of a party; handoff or revive starts the next |
| keeper | a party whose sessions run with Remote Control; only the guild assistant |
| quest | a party's current assignment: a slice of an epic, a whole epic, or a stream with no epic |
| epic, task | planning units owned by SDD and the tracker; guild only observes them |
| raid | named channel several parties join (implemented) |
| raid lead | a party coordinating a raid; a normal local session |
| brief | what a fresh session reads: handoff, task, PR and asks |
| officer, dispatcher | planned roles; the dispatcher launches fresh sessions (see `20261004_dispatcher-launches-fresh-sessions`) |

A party with no live leader is displayed `idle` or `queued` (or `waiting-ask`), never as an anomaly. The stored party state `awaiting-leader` is unchanged. Subagents ("party members") are still not tracked. Metaphor only in nouns; verbs stay literal.

## Consequences

Parties are identity and state, sessions are disposable. Display statuses no longer alarm on a missing session, so `drift`'s `party has no running leader` stays the only liveness finding. Supersedes `20260927_vocabulary`.
