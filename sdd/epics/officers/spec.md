---
epic: officers
type: spec
title: Deterministic watchers that call a model only to fix
status: draft
owner: matpardo
created: 2026-10-04
updated: 2026-10-04
---

# Spec: Deterministic watchers that call a model only to fix

## Goal

Recurring checks run as scripts, and a model is called only when something needs fixing.

## Problem

Leaders spend tokens checking the merge queue, CI, tracker and SDD drift, and open asks. That work is deterministic.

## Scope

- Officers as dispatcher rules with a check script: red main, tracker and SDD drift, stalled PRs, conflicts on hot files, cost over budget.
- On a finding, an officer opens an incident for the owning party or launches one session through the dispatcher.
- A generated summary for the human after an absence, instead of the notice feed.

## Out of scope

- New checks beyond those listed until each existing one has a script.

## Success criteria

- [ ] The leader session no longer polls state; officers' findings reach the right party.

## Security and data

Same as `dispatcher`: opt-in, logged, one launch per party.
