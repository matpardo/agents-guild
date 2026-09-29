---
epic: core-cli
type: tasks
title: Core CLI for coordinating parallel sessions
status: done
updated: 2026-09-28
---

# Tasks: Core CLI for coordinating parallel sessions

## T01 — Event log, projections and identity

**Depends on:** —
**Status:** [x] done — 76272fd

**What:** SQLite event log with reducers and `rebuild`; session → party binding; writes refused while unbound.

## T02 — Parties, quests, tasks, PRs, asks, notices, claims

**Depends on:** T01
**Status:** [x] done — 76272fd

**What:** the write commands, `sync --source gh`, `seed`, `export`.

## T03 — Hooks

**Depends on:** T02
**Status:** [x] done — 76272fd

**What:** `session-start`, `prompt-submit`, `pre-push`; errors contained to one visible line.

## T04 — Human board and asks views

**Depends on:** T02
**Status:** [x] done — 167005c

**What:** asks first, then notices, then one block per party with PRs nested under their tasks; colors only on a TTY.

## T05 — Agent rules as an importable GUILD.md

**Depends on:** T02
**Status:** [x] done — 3849536

**What:** rules ship with the CLI; `install.sh` links them; imported by absolute path.

## T06 — Closing a party cleans up

**Depends on:** T02
**Status:** [x] done

**What:** `guild party close [<party>]` works from a terminal once the session is gone; closing marks the party's quests done, dismisses its open asks, releases its claims and lists tracked PRs still open. `guild quest done <slug>` finishes a single quest.
