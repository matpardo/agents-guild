---
epic: human-ready-prs
type: spec
title: PRs that are really ready for the person
status: active
owner: matpardo
created: 2026-10-20
updated: 2026-10-20
---

# Spec: PRs that are really ready for the person

## Goal

Guild says, per PR and in one place, whether it is ready for the person to review or merge, and what exactly is missing if not, with and without CI.

## Problem

The dev leaves several parties working and comes back to many PRs in Ready with none really ready: unanswered threads, bot comments after the last push, a stale review trace, CI that never ran or was never classified. A project may run CI only with a label, so a push leaves the head with no checks; a main blocked by billing makes every check fail for a cause unrelated to the PR. Today `ready-check`, the party waits and `next` ignore the billing mode, and `next` hands out new tasks while PRs sit stuck.

## Scope

- A human-ready state per PR: Ready, 0 unresolved threads, no comment or review by an author other than the PR author after the head commit, a valid review trace for the head when the project declares a validator, and green CI on the head. With main blocked by billing, or no checks on the head by label design, the state is "ready (CI pending)" and does not block.
- The state shows in `ready-check` and in the merge-queue model (CLI and web).
- Check failures caused by billing are classified.
- Party waits and `next` read the billing mode.
- WIP 1 in `next`: no new tasks while an own Ready PR is not human-ready, not counting drafts nor PRs that only wait for the CI label.
- `guild review-md`.
- A "ready for you" section on the board (CLI and web).
- Minimal per-project config: `human_ready.ci_label`, `human_ready.trace_validator`.
- `README.md` and `GUILD.md` change in every PR that changes behavior.

## Out of scope

- Merging, labeling or marking Ready: guild never does it; the merge is human.
- Applying the CI label.
- Resolving threads.
- Project names.
- Web writes.

## Success criteria

- [ ] `ready-check` prints the human-ready state and what is missing, and exits 0 only when the PR can be merged by hand.
- [ ] With CI behind a label and no checks on the head, the state is "ready (CI pending)" and names the label.
- [ ] A billing failure does not send the PR to "fix failing checks".
- [ ] `next` gives no new task while an own Ready PR is not human-ready.
- [ ] `review-md`, the board and the web list the same PRs, in queue order.
- [ ] A project without config keeps its output, except for the new lines.

## Security and data

The trace validator runs as argv without a shell, with a timeout, in the project clone. `{head_sha}` is validated as hex and `{pr}` as an integer. The comments file is a temporary 0600 file and is deleted. Output is sanitized. Everything is as fresh as the last sync.
