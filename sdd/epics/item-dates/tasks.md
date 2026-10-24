---
epic: item-dates
type: tasks
title: Dates on every item
status: active
updated: 2026-10-24
---

# Tasks: Dates on every item

## T01 — Quest and task dates

**Depends on:** —
**Status:** [x] done

**What:** `created_at` and `updated_at` on quests and quest tasks, set by the reducers, shown on the quest board, the party blocks and the web, with a doctor warning for rows that predate them.

## T02 — PR, claim and party dates

**Depends on:** —
**Status:** [x] done

**What:** `prs.tracked_at`, `claims.created_at` and `updated_at` and `parties.updated_at`, set by the reducers. PRs show tracked and last activity, claims show claimed (kept while the same party renews) and last renewal, parties show the first leader start and last change (start, handoff, resume, close), in the CLI and the web, with the doctor warning covering the new columns.

## T03 — Ask and adventurer dates

**Depends on:** —
**Status:** [ ] pending

**What:** Show created and answered for asks, started and done for adventurers.
