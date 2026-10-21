---
epic: human-ready-prs
type: discovery
title: PRs that are really ready for the person
status: active
updated: 2026-10-20
---

# Discovery: PRs that are really ready for the person

## Decisions

- 2026-10-20: Human-ready is a separate field, not the queue state. `compute` adds `human_state` and `human_missing` next to `state` and `action`, which keep their ordering semantics, because the spec requires unchanged output for unconfigured projects and `next` and the waits move in T05 and T06. Billing comes from the main rows `compute` already receives. The CI label name is resolved where text is printed (`notes()`), so `compute` and `open_pr_records` keep their signatures. T06, T07 and T08 read `human_state` and `HUMAN_READY_STATES`.
- 2026-10-20: The review trace validator runs at sync for Ready PRs only, never in read paths (`ready-check`, web, `compute`), and its result is stored in `pr.synced` as `trace_valid` and `trace_reason`, so a rebuild reproduces it without running the command. A failed run (timeout, launch error, no clone) stores not validated, never valid, and never fails the sync. Invalid blocks the human state, not validated waits.
- 2026-10-20: `ask wait` and `pr wait` only read the database: no sync, no `gh` call, no write. Nothing in guild refreshes PR rows between syncs, so `pr wait` watches `prs.synced_at` on its own clock and exits 4 after 30 minutes without a change, telling the session to sync or install `guild sync-timer`. New comments are counted at sync as `prs.other_author_comments` (comments and reviews by authors other than the PR author, any head, minus notice-only entries) and the baseline lives in the wait process, so a rebuild reproduces the fact and nothing else moves `last_activity_at`. `human_ready.notice_comments` entries need author AND literal text (case-insensitive substring, no regex: dev decision 2026-10-20, so no hostile body can backtrack), so one bot's real review is never swallowed by its notices; the key (dev approved, 2026-10-20) only affects `pr wait`. There is no web counterpart: a blocking process is a session mechanism and the web already shows ask and PR states.
