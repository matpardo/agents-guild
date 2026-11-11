# ADR: `guild party start` takes no quest

- **Date:** 2026-11-11
- **Status:** accepted

## Context

The first plan's surface floated `party start <name> --quest <slug>`. That is a chicken-and-egg requirement: the quest would have to exist before the party that owns it.

## Decision

Phase 1 drops `--quest` from `party start`. A party is created empty, and `guild quest add` binds the new quest to the caller's party.

## Consequences

This matches how every other owned resource (task, PR, ask, claim) is attached to a party: through its own creation command.
