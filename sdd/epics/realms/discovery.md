---
epic: realms
type: discovery
title: Realms connect guilds on one network
status: done
updated: 2026-10-24
---

# Discovery: Realms connect guilds on one network

## Alternatives

| Option | Pros | Cons |
|---|---|---|
| Hub file store over HTTPS (stdlib) | no dependency; runs on a small board; no guild opens a port | the hub is trusted |
| Each guild serves a read-only feed | no hub | every guild opens a port |
| Shared git repo | no server | needs a repo every team can push to; slow |
| Kafka | replayable log | JVM and broker; a client library breaks stdlib-only; the traffic is a few snapshots and files |

## Decisions

- 2026-10-24: a hub that any machine runs, including one with a guild; guilds connect only outbound; the hub is a file store with no commands (decisión del dev).
- 2026-10-24: the status carries counts only, so the panel cannot carry injected text (decisión del dev).
- 2026-10-24: request files land in an inbox only the human reads; hooks never inject them (decisión del dev).
- 2026-10-24: no Kafka; the stdlib hub covers the traffic (decisión del dev).
