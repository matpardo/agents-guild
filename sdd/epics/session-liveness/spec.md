---
epic: session-liveness
type: spec
title: Every party shows whether it is working or stuck
status: done
owner: matpardo
created: 2026-10-04
updated: 2026-10-04
---

# Spec: Every party shows whether it is working or stuck

## Goal

Every party has a visible status, and a session blocked on a permission prompt alerts the human within seconds.

## Problem

In the first real raid a session hit a Claude Code permission prompt and sat there for hours; nothing in guild knew. Several parties stopped silently while the human was away: some waiting on a permission, some idle with queued work. The board shows quests, PRs and asks, but not whether the session behind a party is alive, waiting or done.

## Scope

- `Notification` hook: record when a session waits on a permission prompt, an idle prompt or an elicitation dialog.
- `Stop` hook: record when a session ends its turn.
- `post-tool-use` and `prompt-submit` record that a session is working again, only on a status change.
- A derived party status: `working`, `waiting-permission`, `waiting-input`, `waiting-ask`, `stopped-with-work`, `done`, `awaiting-leader`, `closed`, with its age.
- Surfaces: `guild board` (blocked sessions in NEEDS YOU, status per party), `guild web`, `guild statusline`, `guild revive`, and the raid lead's inbox.
- Optional per-project push command (argv list) run once per waiting episode.
- `guild doctor` checks the new hooks and warns when guild state commands are not allow-listed.

## Out of scope

- Waking or answering a waiting session (see decision `20260928_idle-wake-no-go`).
- Launching sessions on events (`dispatcher` epic).

## Success criteria

- [x] A permission prompt in a bound session shows as `waiting-permission` on the board and fires the push command once.
- [x] Approving it returns the party to `working` with no event per tool call.
- [x] A session that ends its turn with queued work shows `stopped-with-work`.

## Security and data

The notification message is text produced by Claude Code and may quote a command; it is sanitized, truncated and stored with `local` visibility only. The push command is an argv list from the user's own project config, never a shell string, and receives only the party name and wait type.
