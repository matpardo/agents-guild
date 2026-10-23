---
epic: quest-board
type: spec
title: Prepare quests ahead for parties to take
status: done
owner: matpardo
created: 2026-10-23
updated: 2026-10-23
---

# Spec: Prepare quests ahead for parties to take

## Goal

The human or a planning session prepares quests before any party exists, and parties take them from a quest board.

## Problem

A quest exists only once a party creates it, so planned work lives in SDD and in the human's head until a session starts. Nothing lists the synced SDD tasks no quest covers, and `guild next` offers nothing to a party with an empty queue.

## Scope

- A quest may have no party: an open quest (`quests.party` NULL, nullable by migration). A task inside an open quest counts as taken for other quests, `task add` and claims; an adventurer may still start on it with `adventurer start --task`.
- `guild quest add --open` creates one from the human's terminal (no session), from a party session or from an adventurer. It keeps today's checks: synced epic and tasks, and tasks taken by another quest or claim are refused.
- `guild quest take <slug>` gives an open quest to the session's party. A task an adventurer holds stays with the adventurer; the party gets the rest and `guild next` skips the held one.
- `guild quest release <slug>` returns a quest to the board while every task is queued, with no open PR and no claim.
- `guild quest board [--project <name>]` lists open quests and, per synced epic, the tasks no quest covers.
- `guild next` offers "take open quest X" to a party with nothing queued.
- The web board gets a quest board section: create an open quest from an epic's free tasks, assign it to a party, release it. Every write goes through `sendPost` and the same `guild/commands` functions.
- `README.md` and `GUILD.md` change with the code.

## Out of scope

- Starting a party session from the board: the human launches it and the session runs `quest take`.
- Priorities or estimates on open quests; SDD order still rules.

## Success criteria

- [x] An open quest created in the CLI or the web is taken by a party and shows under it.
- [x] `guild quest board` and the web list every synced task no quest covers.
- [x] A party with nothing queued is offered an open quest of its project.
- [x] Open, taken and released quests survive `guild rebuild`.

## Security and data

Local events only. Titles pass `validate_field`. Taking or releasing requires the owning or taking party's own session, or the web token; the web assign action is the human's.
