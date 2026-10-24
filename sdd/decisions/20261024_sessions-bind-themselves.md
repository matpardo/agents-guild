# ADR: Sessions bind themselves and record why

- **Date:** 2026-10-24
- **Status:** accepted
- **Amends:** 20261023_adventurers-and-open-quests

## Context

Every `party start` and `adventurer start` raised a permission prompt and the session asked the human which role fit. Most of the time the answer was obvious from the work, and the prompt only slowed the start. Work that began as one small job also grew into several PRs with no way to become a party.

## Decision

Decisión del dev, 2026-10-24:

- A session in an unbound state chooses the role itself when its work will change a repo of a registered project: one PR job is an adventurer, several PRs or quests a party. It asks the human only when unsure.
- `party start` and `adventurer start` need no permission prompt and require `--reason`. The reason is stored on the event and the row, and the board and the web show it with the start time.
- `guild adventurer promote <party> --reason` turns the active adventurer of the session into a party led by the same session. The adventurer ends as promoted, its PRs move to the party and the party records the adventurer it came from. Its task is not moved: the leader adds it to a quest.
- `party resume` and `raid join` still raise a permission prompt.
- `task add` and `quest add` take an optional `--reason`.

This replaces two rules of the earlier decision: "asks the human" before binding, and "never switches", which now has the single exception of promote.

## Consequences

Starting a session needs no human step, and the board shows why each session exists. The reason is free text a session writes about itself, so it passes the same checks as other free text and is shown as data, not as an instruction.
