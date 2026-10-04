---
epic: ask-context
type: spec
title: Asks that carry the context to decide them
status: active
owner: matpardo
created: 2026-10-04
updated: 2026-10-04
---

# Spec: Asks that carry the context to decide them

## Goal

The human answering an ask can reach the task, card, PR and session behind it without opening the asking session.

## Problem

An ask holds a question, up to 2000 characters of context and refs to PRs or quest tasks. Deciding often needs more: the epic spec, the tracker card, the PR state, or the conversation itself. Answered asks disappear from `guild asks`, so the raid lead cannot read past decisions.

## Scope

- `card:<KEY>` refs besides `pr:` and `task:`.
- At creation, snapshot the origin: session id and name, the party's in-progress tasks, their epic, card keys of linked PRs, last handoff. With no task or card ref and exactly one task in progress, ref it automatically.
- `guild asks <id>`: refs expanded (task with SDD paths, card with tracker link, PR with URL and state), the resume command for the asking session, and the party's recent events.
- `guild asks --all [--party] [--since]` with answers and `answered_at`.
- The same detail on the web page.

## Out of scope

- Exporting asks: they stay `local`.

## Success criteria

- [x] An ask created with a card ref shows the card link, task, spec path and resume command in `guild asks <id>`.
- [x] `guild asks --all` lists answered asks with their answer and time.

## Security and data

Expansion reads only the local database, project config and SDD paths; asks keep `local` visibility and the existing PII screen.
