---
epic: merge-queue
type: tasks
title: Merge queue for raids and parties
status: active
updated: 2026-09-29
---

# Tasks: Merge queue for raids and parties

## T01 — Diff data from gh sync

**Depends on:** —
**Status:** [x] done

**What:** `sync --source gh` fetches changed files, additions, deletions and creation time in one call for open PRs of raid members or parties holding `area:` claims; stores `prs.additions`, `prs.deletions`, `prs.created_at` and `pr_shared_areas`; a fetch failure is a sync failure and keeps the previous rows.

## T02 — Queue ordering

**Depends on:** T01
**Status:** [x] done

**What:** pure `guild/merge_queue.py`: eligible and blocked PRs with exact reasons, topological order over task dependencies, pins and shared-area overlap, a reason per position.

## T03 — Pins

**Depends on:** T02
**Status:** [x] done

**What:** `guild merge-queue pin|unpin`, events `merge_queue.pinned|unpinned`, projection `merge_queue_pins`, authority rules and cycle rejection.

## T04 — CLI

**Depends on:** T02, T03
**Status:** [ ] pending

**What:** `guild merge-queue [--raid | --party]` with default scope rules and read-only output, and a `next to merge` line on `guild board`.

## T05 — Web

**Depends on:** T02
**Status:** [ ] pending

**What:** board model `merge_queues` and a read-only merge queue section on the page that respects the raid and party filters.
