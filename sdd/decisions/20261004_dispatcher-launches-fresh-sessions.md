# ADR: The dispatcher launches fresh sessions, never wakes idle ones

- **Date:** 2026-10-04
- **Status:** accepted

## Context

Parties stop when nothing gives them a turn. Decision `20260928_idle-wake-no-go` rules out waking an idle session through its private socket. Launching a new session with the public `claude` CLI, as `revive` already does in tmux, crosses no such boundary.

## Decision

The dispatcher acts only through public interfaces: guild commands, `gh`, and new `claude` sessions launched in the `guild` tmux session with a task brief. It never writes to an existing session. Every rule is opt-in per project, dry-run until enabled, recorded as an event, and limited to one live launch per party. It launches only parties that handed off (state `awaiting-leader`), whose previous session is no longer running, inside a `guild` tmux session it never creates itself. The permission mode is named in the project config (`manual`, `acceptEdits` or `auto`) and never exceeds it: the launch uses the more restrictive of the configured mode and the party's last mode, ordered `plan` < `manual` < `acceptEdits` < `auto`. A trigger that finds the party busy is deferred and retried for 24 hours instead of dropped. Each trigger is decided once: the intent is recorded before the launch, so a crash never launches twice. A launch that does not bind within ten minutes is reported and blocks the party until a human resumes it.

## Consequences

Answers, red CI and merges reach work without a human nudge. Each launch costs a fresh context instead of reusing one, which `cost-metering` must show is cheaper than long sessions. `20260928_idle-wake-no-go` stays in force. A session that ends idle keeps its party out of dispatch until it is closed. Lifecycle commands stay in `sync`.
