# ADR: Solo players launch on trigger

- **Date:** 2026-11-01
- **Status:** accepted

## Context

Health jobs only launch by hand: the board says a job is due and the human runs `guild adventurer launch`. On 2026-10-12 the dev objected to launching work on a timer (decisión del dev); the objection was really about invasive systemd processes. Guild has no daemon now, and a red main or a stuck Dependabot PR waits for a human to notice it.

## Decision

Decisión del dev, 2026-11-01: guild ships built-in per-repo solo players, `red-main` and `dependabot`, declared in the project config key `solo_players`. The sync detects their triggers (a red main, an unmergeable Dependabot PR, a failing Dependabot update run). They may be launched on trigger by the due-jobs ticker, which lands in a follow-up. Guards:

- opt-in config per repo, absent means nothing;
- one window per job;
- one active adventurer per job;
- a 1h cooldown after a report;
- launches only from the human terminal, never from inside a session.

## Consequences

Each solo player is also a derived health job, so adventurers, hooks and the board reuse the health-job path. A red main or a stuck Dependabot update gets a session without the human typing a command, once the ticker lands.

Revisit when launches pile up or spend surprises.
