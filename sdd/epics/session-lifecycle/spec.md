---
epic: session-lifecycle
type: spec
title: Handoffs that clean up and sessions that respawn
status: draft
owner: matpardo
created: 2026-10-04
updated: 2026-10-04
---

# Spec: Handoffs that clean up and sessions that respawn

## Goal

Handoff files and per-session state are deleted once no one needs them, and a long-lived keeper session reachable through Remote Control respawns itself at its context limit.

## Problem

Every handoff writes a file that is never deleted, and per-session state (`ctx`, hint and nudge markers) accumulates for sessions long gone. Remote access to the running work needs one session that stays reachable; today a handoff ends it and the next generation must be launched by hand, without Remote Control.

## Scope

- Mark a handoff consumed when the next generation binds.
- Retention: keep the latest handoff of every open party; delete a superseded one once consumed; keep a closed party's last handoff for `handoff_retention_days` (explicit project config).
- `guild handoff prune [--dry-run]`, also run by the sync timer and on `party close`; prunes state markers of sessions that no longer exist.
- `guild handoff --respawn`: launch the next generation in the `guild` tmux session and close the old window once the new one binds, only if guild launched it.
- Keeper parties (`party start --keeper`): launched with `--remote-control`; their context nudge asks for `handoff --respawn`; `revive` relaunches them with Remote Control.

## Out of scope

- Claude Code transcripts: Claude Code owns their retention.

## Success criteria

- [ ] `handoff prune --dry-run` on a real data directory lists only superseded or expired files and dead-session markers.
- [ ] A keeper at its threshold respawns with Remote Control and the old window closes.

## Security and data

Deletion is limited to files under guild's own data and state directories, resolved with `names.ensure_within`. Remote Control is a Claude Code feature behind the user's own login; guild only passes the flag.
