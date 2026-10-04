---
epic: execution-profiles
type: spec
title: Accounts, providers and models per role
status: draft
owner: matpardo
created: 2026-10-04
updated: 2026-10-04
---

# Spec: Accounts, providers and models per role

## Goal

Each project or role runs with its own account, provider and model, chosen by guild when it launches a session.

## Problem

Every session inherits the default model, so mechanical work (triage, summaries, parsing) and reviewers run on the most expensive one. Different projects may need different accounts, and nothing routes them.

## Scope

- Profiles in guild config: provider, credential location (e.g. a `CLAUDE_CONFIG_DIR`), model, budget; bound per guild, project or role.
- Routing by task type: small or local model for periodic triage and summaries, mid-size for development and review, largest for consequential judgment and the final review round.
- Account and provider recorded on every `cost.sampled` event.

## Out of scope

- Storing credentials: profiles point at them, never contain them.

## Success criteria

- [ ] Two projects run on two accounts and `guild cost` separates them.

## Security and data

Credentials never enter events, notices or the bus; only the profile name does.
