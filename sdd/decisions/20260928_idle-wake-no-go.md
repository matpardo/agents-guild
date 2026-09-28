# ADR: No waking of idle sessions

- **Date:** 2026-09-28
- **Status:** accepted

## Context

An answered ask reaches a session only on its next prompt or tool call. An idle session never wakes on its own. Each session exposes a local socket and feature flags (`notify_idle`) in `~/.claude/sessions/*.json`.

## Decision

Do not use that socket. Its protocol is undocumented, versioned internally and authenticated with a private per-session key file. Guild would break on any protocol change and would cross a trust boundary it has no business crossing.

## Consequences

Busy sessions get answers mid-turn through the `PostToolUse` hook; idle sessions still need a human nudge. Revisit if Claude Code publishes a contract for this.
