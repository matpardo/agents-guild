---
epic: merge-queue
type: tasks
title: Merge queue for raids and parties
status: done
updated: 2026-09-29
---

# Tasks: Merge queue for raids and parties

## T01 — Diff data from gh sync

**Depends on:** —
**Status:** [x] done — #30

**What:** `sync --source gh` fetches changed files, additions, deletions and creation time in one call for open PRs of raid members or parties holding `area:` claims; stores `prs.additions`, `prs.deletions`, `prs.created_at` and `pr_shared_areas`; a fetch failure is a sync failure and keeps the previous rows.

## T02 — Queue ordering

**Depends on:** T01
**Status:** [x] done — #30

**What:** pure `guild/merge_queue.py`: eligible and blocked PRs with exact reasons, topological order over task dependencies, pins and shared-area overlap, a reason per position.

## T03 — Pins

**Depends on:** T02
**Status:** [x] done — #30

**What:** `guild merge-queue pin|unpin`, events `merge_queue.pinned|unpinned`, projection `merge_queue_pins`, authority rules and cycle rejection.

## T04 — CLI

**Depends on:** T02, T03
**Status:** [x] done — #30

**What:** `guild merge-queue [--raid | --party]` with default scope rules and read-only output, and a `next to merge` line on `guild board`.

## T05 — Web

**Depends on:** T02
**Status:** [x] done — #30

**What:** board model `merge_queues` and a read-only merge queue section on the page that respects the raid and party filters.

## T06 — Store review decision, merge state and base branch

**Depends on:** T01
**Status:** [x] done — #94

**What:** `sync --source gh` stores `prs.review_decision`, `prs.merge_state` and `prs.base_branch`; `UNKNOWN` merge state keeps the previous value; old `pr.synced` events replay with the fields empty.

## T07 — Count unresolved review threads

**Depends on:** T06
**Status:** [x] done — #0

**What:** `sync --source gh` stores `prs.unresolved_threads` for open PRs through a `gh api graphql` query; a query failure is a sync failure and keeps the previous count; merged and closed PRs are not queried.
