---
epic: specs-in-repo
type: spec
title: Specs live in the code repo
status: done
owner: matpardo
created: 2026-09-28
updated: 2026-09-28
---

# Spec: Specs live in the code repo

## Goal

agents-guild keeps its own SDD in `sdd/`, updated in the same PR as the code.

## Problem

A separate docs repo doubles the PRs and lets specs lag the code. See decision `20260928_specs-in-repo`.

## Scope

- `sdd/` with epics, decisions and templates, adapted from the separate-repo SDD pattern.
- A test that validates frontmatter and parses every `tasks.md` with guild's adapter.
- Epics for the work already shipped, marked done, and for what comes next.

## Out of scope

- Changing how other projects organize their specs.

## Success criteria

- [x] `python3 -m unittest` fails on a malformed spec.
- [x] `guild sync --source sdd` reads this repo's epics.

## Security and data

N/A: documentation only.
