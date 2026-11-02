# ADR: Solo players launch on trigger

- **Date:** 2026-11-01
- **Status:** accepted

## Context

Health jobs only launch by hand: the board says a job is due and the human runs `guild adventurer launch`. On 2026-10-12 the dev objected to launching work on a timer (decisión del dev); the objection was really about invasive systemd processes. Guild has no daemon now, and a red main or a stuck Dependabot PR waits for a human to notice it.

## Decision

Decisión del dev, 2026-11-01: guild ships built-in per-repo solo players, `red-main` and `dependabot`, declared in the project config key `solo_players`. The sync detects their triggers (a red main, an unmergeable Dependabot PR, a failing Dependabot update run). They launch on trigger: the ticker of `guild web`, the hooks and `pr wait` spawn `guild solo tick` every 10 minutes, and it opens a window for each due player. Guards:

- opt-in config per repo, absent means nothing;
- one window per job: the tick closes the leftover window of a `due` player before launching it;
- one active adventurer per job;
- a 1h cooldown after a report;
- a 24h cooldown instead of 1h when the trigger text equals the one of the last launch;
- a launch debounce: a launch younger than the cooldown keeps the player cooling;
- a red-main player stays `fixing`, and is not launched, while a PR of its repo tracked as fixing main is open;
- a player whose active adventurer lost its session is `stalled` and is not launched until the human dismisses that adventurer;
- each launch posts to the read-only solo channel, not to a project notice, so launches do not interrupt other sessions;
- launches only from the human terminal, never from inside a session.

## Consequences

Each solo player is also a derived health job, so adventurers, hooks and the board reuse the health-job path. A red main or a stuck Dependabot update gets a session without the human typing a command.

Revisit when launches pile up or spend surprises.
