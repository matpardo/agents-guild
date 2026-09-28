# ADR: Vocabulary (guild, party, quest, epic, task, raid)

- **Date:** 2026-09-27
- **Status:** accepted

## Context

Each term costs context in every hook output and risks colliding with Claude Code's own terms (agent, subagent, session, team). A term earns its place only if it names something the system persists or routes on.

## Decision

| Term | Meaning |
|---|---|
| guild | one install: database and config |
| party | durable work lineage that survives handoffs; owns quests, PRs, claims |
| leader | the current session of a party (attribute, no commands) |
| quest | a party's current assignment: a slice of an epic, a whole epic, or a stream with no epic |
| epic, task | planning units owned by SDD and the tracker; guild only observes them |
| raid | named channel several parties join (planned) |

Subagents ("party members") are not tracked: they are ephemeral and never see prompt hooks. Metaphor only in nouns; verbs stay literal.

## Consequences

Party identity solves session renames across handoffs. Keeping `epic` and `task` literal avoids translating between guild, SDD and the tracker.
