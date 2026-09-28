---
epic: web-and-federation
type: spec
title: Web view and guilds across machines
status: draft
owner: matpardo
created: 2026-09-27
updated: 2026-09-28
---

# Spec: Web view and guilds across machines

## Goal

Read the board from a browser and let the agents of other team members receive guild-visible notices.

## Problem

The board lives in one terminal on one machine. Teammates' agents cannot learn that a fix is in progress.

## Scope

- Web view fed by `guild export --visibility guild`.
- Federation: per-party append-only event files in a shared repo (conflict-free); only guild-visible kinds leave the machine (notices, claims, PR one-liners).
- Per-person identity and authentication.

## Out of scope

- Sharing asks, handoffs or free-text context across machines.

## Success criteria

- [ ] A notice from one machine reaches a session on another, labeled with its origin.

## Security and data

Crossing machines makes identity and provenance real security boundaries; the single-user trust model no longer holds and must be redesigned first.
