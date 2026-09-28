---
epic: web-board
type: spec
title: Web view of the guild board
status: draft
owner: matpardo
created: 2026-09-28
updated: 2026-09-28
---

# Spec: Web view of the guild board

## Goal

See the guild board, asks and notices in a browser, with a clearer layout than the terminal allows.

## Problem

`guild board` is readable but dense: many parties, PRs and asks compete for one terminal screen, and there is no way to filter, collapse or link out to PRs and cards.

## Scope

- Read-only web view fed by `guild export` (JSON), so the core CLI stays unchanged and the view can use whatever stack fits.
- Asks first, then parties with quests, tasks and PRs; links to PRs and cards; filters by party and state.
- Later, if useful: answering asks from the page (writes go through the CLI, never directly to the database).

## Out of scope

- Other machines (see `federation`).
- Replacing the terminal board.

## Success criteria

- [ ] A human can find every open ask and its context without opening a terminal.

## Security and data

The export carries free text written by agents. The page must escape it and must not be served beyond localhost without authentication.
