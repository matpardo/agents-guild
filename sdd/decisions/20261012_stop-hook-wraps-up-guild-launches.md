# ADR: The Stop hook wraps up an unattended guild launch

- **Date:** 2026-10-12
- **Status:** accepted

## Context

A party whose leader session ends without `guild handoff` stays `active`
until a human notices. `20261004_dispatcher-launches-fresh-sessions` and its
amendment of `session-autopilot` T04 already close this gap for a session
whose process has actually died: the dispatcher writes an automatic handoff
once both the leader pid and its guild-recorded tmux window are gone. That
leaves a narrower case open: a guild-launched session that is still alive,
in a still-open window, but whose agent simply forgot to hand off, is
blocked on an answered ask it never re-read, or finished its turn and sits
idle with nobody looking. Such a session has no dead pid for the dispatcher
to notice, so it is left stuck indefinitely.

## Decision

The `Stop` hook wraps up a session only when every one of these holds, and
any doubt means it does nothing:

- the session's `GUILD_RESUME` matches the party it is bound to (or, for a
  session that already ran a plain `guild handoff`, matches the party row a
  join of `leaders`/`parties` resolves for it) — so it launched this
  generation of this party, never a human-started session or a `revive
  --resume` of a different party;
- the party is not a keeper (Remote Control keeper parties stay out of
  scope, like every other autopilot step in this epic);
- there are no pending background tasks and no scheduled crons
  (`background_tasks`/`session_crons` both empty in the Stop payload; a
  missing field is treated as "pending", not "empty");
- nobody has typed a real prompt into the session since it started: a
  `prompt-submit` marker (`attended-<session>`) is written the first time
  the prompt is not one of guild's own automatic prompts (the resume prompt,
  or a background subagent's `<task-notification>` report) — once written,
  it blocks wrap-up forever for that session;
- the transcript shows no usage limit, and a missing or unreadable
  transcript also counts as "cannot tell" and skips, never as "no limit";
- guild recorded the tmux window of this generation and the session's own
  pane is still in it — the same check `guild handoff --close` already
  makes, now moved to `tmux_windows.closable_pane` so both share it.

When all of that holds, the first `Stop` blocks once with a reason asking
the agent to run `guild handoff --close` itself, and records a
`wrapup-<session>` marker. The next `Stop` — whether Claude Code reports
`stop_hook_active: true` or the marker alone says the block already
happened, since `stop_hook_active`'s exact behavior across tool-calling
continuations is not fully documented — writes the automatic handoff and
closes the pane with `tmux kill-pane`, never the window. A session that
already ran a plain `guild handoff` and stops with its pane still the
recorded one gets the pane closed the same way, writing no second handoff.

This relies on one undocumented detail of Claude Code: that a background
subagent's task-notification report is a `UserPromptSubmit` prompt starting
with the literal `<task-notification>` prefix. If that prefix ever changes,
the check simply stops matching it, treating that report like a human
prompt — the session gets marked attended and wrap-up never fires for it,
which fails safe (a human-run session is never closed early) at the cost of
leaving that one session unwrapped, same as any other doubt in this list.

## Consequences

This amends `20261004_dispatcher-launches-fresh-sessions`'s "a session that
ends idle keeps its party out of dispatch until it is closed" a second
time, narrower than T04's amendment: that sentence no longer holds for a
guild-launched, non-keeper session that is truly unattended (no live
prompt, no pending work, no usage limit) in a window guild still records —
such a session is wrapped up and relaunched like any other handed-off
party. It still holds for a human-started session, a keeper, a session
still doing background work, and any session a real prompt touched.
