---
epic: federation
type: spec
title: Guilds across machines
status: draft
owner: matpardo
created: 2026-09-27
updated: 2026-10-24
---

# Spec: Guilds across machines

## Goal

The agents of other team members receive guild-visible notices and claims.

## Problem

A guild lives on one machine. Teammates' agents cannot learn that a fix is in progress or that an area is claimed.

## Scope

- Per-party append-only event files in a shared repo (conflict-free); only guild-visible kinds leave the machine (notices, claims, PR one-liners).
- Per-person identity and authentication.
- One guild per machine, standalone by default; replication of guild-visible events through the realm of `realms` (a lightweight broker such as NATS JetStream, or plain HTTP replication).
- Merge queue and claims scoped per repository, not per guild, once two guilds work on one repository; hot-file serialization (`conflict-hotspots`) moves to the realm with them.
- An HTTP API for guild, needed before the main development moves to another machine.

## Out of scope

- Sharing asks, handoffs or free-text context across machines.
- Secrets on the bus: it carries events only.

## Success criteria

- [ ] A notice from one machine reaches a session on another, labeled with its origin.

## Depends on

- `web-board`: the shared view comes first; federation may reuse its backend.
- `realms`: the hub, identity and status view between guilds.

## Security and data

Crossing machines makes identity and provenance real security boundaries; the single-user trust model no longer holds and must be redesigned first.
