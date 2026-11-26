---
epic: usage-limit
type: tasks
title: Sessions stopped by the usage limit show as waiting, not dead
status: done
updated: 2026-11-26
---

# Tasks: Sessions stopped by the usage limit show as waiting, not dead

## T01 — Spec

**Depends on:** —
**Status:** [x] done

**What:** spec for the `waiting-limit` status fed by the `StopFailure` hook.

## T02 — Waiting-limit status

**Depends on:** T01
**Status:** [x] done

**What:** `guild hook stop-failure`, wait `limit` mapped to `waiting-limit` in board and web, hook registered in the expected hook list, docs.

## T03 — Name the limit in the reset wait

**Depends on:** T02
**Status:** [x] done

**What:** the `limit-reset` wait says whether the 5h or the weekly limit was hit, read from `quotaLimits.rateLimitType`, and shows the reset date when it is not today.
