---
epic: conflict-hotspots
type: spec
title: Serialize work on files that keep conflicting
status: draft
owner: matpardo
created: 2026-10-04
updated: 2026-10-04
---

# Spec: Serialize work on files that keep conflicting

## Goal

Guild learns which files conflict on every merge and serializes the branches that touch them.

## Problem

In the first raid a schema dump file rewritten by every database migration conflicted on each merge: every branch with a migration collided with every other. Routes, lockfiles and changelogs behave the same way. Nothing records these conflicts, so every party rediscovers them.

## Scope

- Record conflicts: the `post-tool-use` hook parses `CONFLICT ... Merge conflict in <path>` from `git rebase|merge|cherry-pick|pull` output; `sync --source gh` records candidate files when a PR becomes conflicting (PR files intersected with files changed on the base since the merge base).
- Hot-file register: a path is hot after `hot_files.threshold` conflicts within `hot_files.window_days`, or from day one when it matches `hot_files.seed`.
- `guild hotfiles [--project]` with counts and holder.
- Pre-push and pre-edit auto-claim a hot file for the party whose branch touches it, reusing shared-area claims and release on merge.
- The merge queue orders PRs touching the same hot file back to back; a merge touching one tells the other owners to rebase.

## Out of scope

- Two migrations with the same version: already announced by `sync`.
- Resolving conflicts automatically.

## Success criteria

- [ ] Replaying a real rebase conflict marks the file; a second branch touching it is told who holds it.

## Security and data

Only file paths and branch names are stored; hook parsing reads command output already in the session.
