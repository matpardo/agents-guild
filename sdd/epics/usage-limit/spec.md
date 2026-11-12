---
epic: usage-limit
type: spec
title: Sessions stopped by the usage limit show as waiting, not dead
status: active
owner: matpardo
created: 2026-11-11
updated: 2026-11-11
---

# Spec: Sessions stopped by the usage limit show as waiting, not dead

## Goal

The board tells a session that hit the account usage limit apart from one that stopped or died, so the human knows to resume it once the limit resets.

## Problem

When Claude Code ends a turn because of the usage limit, the `Stop` hook does not fire. The session's last status stays `working`, and once its process ends the board shows it as gone or `stopped without report`. Nothing says it is waiting for the limit to reset.

## Scope

- Claude Code fires a `StopFailure` hook instead of `Stop` when a turn ends on an API error. Its input carries `error`: `rate_limit` or `billing_error` mean a limit was hit.
- A new hook `guild hook stop-failure` reads `error`. On `rate_limit` or `billing_error` it records `session.waiting` with wait `limit`. Any other error records `session.stopped`, as `Stop` would.
- Wait `limit` maps to board status `waiting-limit`, shown in `guild board` and the web board, with its own colour.
- The status clears through the existing `working` transition on the next prompt or tool call.
- The hook also starts the due background jobs and runs the project's `notify` command, as the blocking waits do.
- `guild wire-settings`, `unwire-settings` and `guild doctor` know the new hook through the expected hook list.

## Out of scope

- The reset time. `StopFailure` has no field for it. The statusline input has `rate_limits.*.resets_at`, but only while the session runs and only through the user's statusline script.
- Resuming a session on its own after the reset.

## Success criteria

- [ ] A bound session whose turn ends with `error: rate_limit` shows `waiting-limit` on the board and the web.
- [ ] Another error such as `server_error` shows `stopped`.
- [ ] An unbound session records nothing.
- [ ] The next prompt in that session shows it `working` again.

## Security and data

- The hook stores only the error kind as the wait message. It never stores `error_details` or `last_assistant_message`, which can hold conversation text.
- Risk: the Claude Code docs do not say that the subscription limit maps to `rate_limit`. Check it on a real limit hit and widen the mapping if needed.
