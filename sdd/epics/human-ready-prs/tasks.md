---
epic: human-ready-prs
type: tasks
title: PRs that are really ready for the person
status: active
updated: 2026-10-20
---

# Tasks: PRs that are really ready for the person

## T01 — Sync reads head freshness facts

**Depends on:** —
**Status:** [ ] pending

**What:** `sync --source gh` stores per PR the number of comments and reviews by other authors after the head commit, and whether the project's CI label is on the PR.

**Acceptance:**
- [ ] `prs.comments_after_head` and `prs.ci_label` are filled by sync and survive `guild rebuild`; a project without `human_ready.ci_label` stores no label flag.

## T02 — Billing-caused PR check failures are classified

**Depends on:** T01
**Status:** [ ] pending

**What:** A PR whose checks fail while main is blocked by billing is classified as billing, not as a real failure.

**Acceptance:**
- [ ] The classification is stored and no output sends such a PR to fix failing checks.

## T03 — human-ready in the queue and ready-check

**Depends on:** T01, T02
**Status:** [ ] pending

**What:** The merge-queue model computes the human-ready state per PR and `ready-check` prints it with what is missing.

**Acceptance:**
- [ ] `ready-check` exits 0 only when the PR can be merged by hand; CLI and web show the same state.

## T04 — Review trace validator

**Depends on:** T03
**Status:** [ ] pending

**What:** `human_ready.trace_validator` runs a project command that validates the review trace for the head.

**Acceptance:**
- [ ] The validator runs as argv without a shell, with a timeout; `{head_sha}` is hex and `{pr}` an integer; the comments file is temporary 0600 and deleted.

## T05 — Waits and next read the billing mode

**Depends on:** T03
**Status:** [ ] pending

**What:** Party waits and `next` read the billing mode of main.

**Acceptance:**
- [ ] Neither names a billing-failing PR as needing a fix.

## T06 — WIP 1 in next

**Depends on:** T05
**Status:** [ ] pending

**What:** `next` gives no new task while an own Ready PR is not human-ready.

**Acceptance:**
- [ ] Drafts and PRs that only wait for the CI label do not count.

## T07 — guild review-md

**Depends on:** T03
**Status:** [ ] pending

**What:** `guild review-md` lists the PRs ready for the person as markdown, in queue order.

**Acceptance:**
- [ ] Same PRs and order as the queue.

## T08 — Ready for you on the board

**Depends on:** T03
**Status:** [ ] pending

**What:** The board (CLI and web) gets a "ready for you" section.

**Acceptance:**
- [ ] CLI and web list the same PRs in queue order.
