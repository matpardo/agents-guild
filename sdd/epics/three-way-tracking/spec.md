---
epic: three-way-tracking
type: spec
title: Track work across guild, SDD, tracker and GitHub
status: active
owner: matpardo
created: 2026-09-27
updated: 2026-09-28
---

# Spec: Track work across guild, SDD, tracker and GitHub

## Goal

One unit of work is followed across guild, SDD, the card tracker and GitHub, and every disagreement between them is visible.

## Problem

The same task lives in up to four places that drift silently: SDD lags because it is updated through PRs, cards move on their own, PRs merge from a phone. The resolver already ranks sources (guild > tracker > SDD) but the tracker slot is empty and nothing lists the discordances.

## Scope

- Card keys read from a dedicated line (`**JIRA:** KEY`), not only from the heading.
- A tracker adapter (first implementation: JIRA via `acli`) that observes card status and parent, read-only.
- `guild drift [--epic X]`: numbered discordances with each source's opinion.
- Raids: named channels parties join, as a deterministic audience for notices.

## Out of scope

- Writing to SDD or the tracker: fixing drift stays with humans and existing skills.

## Success criteria

- [ ] `guild drift` on real data lists discordances that a human confirms by hand.
- [ ] `guild next` uses tracker status when guild has no opinion.

## Security and data

Tracker content is external text: same sanitizing and framing as SDD. Credentials stay in `acli`; guild never stores them.
