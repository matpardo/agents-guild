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
