# ADR: Adventurers, open quests and one identity per session

- **Date:** 2026-10-23
- **Status:** accepted, amended by 20261024_sessions-bind-themselves
- **Supersedes:** 20261004_vocabulary-short-sessions

## Context

Guild only sees work done inside a party. One-off sessions leave no record, so nobody knows what they left pending. A quest exists only once a party creates it, so work cannot be prepared ahead for a party to take later. A bound session can start or resume a second party and keep leading both. The dispatcher, keeper parties, the raid lead and officers retired (`20261014_board-shows-waits-no-dispatcher`).

## Decision

Decisión del dev, 2026-10-23:

| Term | Meaning |
|---|---|
| guild | one install: database and config |
| party | durable work lineage that survives handoffs; owns quests, PRs, claims |
| leader | the live session of a party: zero or one (attribute, no commands) |
| generation | one session of a party; handoff or revive starts the next |
| adventurer | one session doing one job on one project: one task or a one-off change; no generations, no handoff; it ends by reporting what is pending |
| quest | a planned slice of work: part of an epic, a whole epic, or a stream with no epic; owned by zero or one party, never by an adventurer |
| open quest | a quest no party owns yet; listed on the quest board until a party takes it |
| quest board | the open quests and the synced SDD tasks no quest covers, per project |
| health job | a recurring adventurer job a project declares; the board shows when it is due |
| epic, task | planning units owned by SDD and the tracker; guild only observes them |
| raid | named channel several parties join |
| brief | what a fresh session reads: handoff, task, PR and asks |
| keeper, raid lead, dispatcher, officer | retired |

Rules:

- A session is one identity for its whole life: the leader of one party, one adventurer, or unbound. It never switches.
- Before a session works on a registered project, it asks the human whether the work is a party or an adventurer.
- A party's PR always belongs to one of its tasks. A PR outside any task belongs to an adventurer.
- An adventurer may do one task of an open quest or of a synced epic. It never takes or owns a quest.
- Every session that stops reports what is pending: a party through `guild handoff`, an adventurer through `guild adventurer done --pending`.
- The human launches every session, health jobs included. Nothing starts on a timer.

## Consequences

The board shows every session that works on a project and what each one left. Work can be planned as open quests before any party exists. Loose PRs of parties disappear. Old databases can hold a session that leads two parties; a drift finding reports it. Metaphor only in nouns; verbs stay literal.
