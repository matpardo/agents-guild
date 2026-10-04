# ADR: The dispatcher launches fresh sessions, never wakes idle ones

- **Date:** 2026-10-04
- **Status:** proposed

## Context

Parties stop when nothing gives them a turn. Decision `20260928_idle-wake-no-go` rules out waking an idle session through its private socket. Launching a new session with the public `claude` CLI, as `revive` already does in tmux, crosses no such boundary.

## Decision

The dispatcher acts only through public interfaces: guild commands, `gh`, and new `claude` sessions launched in the `guild` tmux session with a task brief. It never writes to an existing session. Every rule is opt-in per project, dry-run until enabled, recorded as an event, and limited to one live launch per party.

## Consequences

Answers, red CI and merges reach work without a human nudge. Each launch costs a fresh context instead of reusing one, which `cost-metering` must show is cheaper than long sessions. `20260928_idle-wake-no-go` stays in force.
