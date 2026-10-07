---
epic: merge-queue
type: spec
title: Merge queue for raids and parties
status: done
owner: matpardo
created: 2026-09-29
updated: 2026-10-07
---

# Spec: Merge queue for raids and parties

## Goal

Guild produces an ordered list of the tracked PRs that are ready to merge, with the reason for every position, so a raid lead or a party can tell the human what to merge next.

## Problem

In the first raid several PRs became ready at once and some touched the same shared file. The parties agreed the order through notices, which go stale as soon as a PR merges, closes or breaks CI. Nobody could see one current, explained order.

## Scope

- `sync --source gh` stores the changed shared-area globs and the diff size of open PRs of parties in a raid or holding an `area:` claim.
- A pure ordering module: eligible PRs, blocked PRs with exact reasons, and a topological order over SDD task dependencies, pins and shared-area overlap (smaller diff first, then earlier created, then lower number).
- Pins: `guild merge-queue pin|unpin <repo#a> --before <repo#b>`, recorded as events with their author, authority checked, cycles rejected.
- `guild merge-queue [--raid <name> | --party <name>]` and a `next to merge` line on `guild board`.
- A merge queue section in `guild web`, read-only.
- A PR's type, read from its branch prefix and overridable with `pr set --type`, shown as a label wherever a PR is shown.
- Urgency marks `pr set --fixes-main` and `--fixes-flaky`: labels, and first position among the PRs that are free to go, never ahead of a task dependency or a pin.

## Out of scope

- Merging, rebasing or updating branches. Guild never merges: the queue is advice for a human.
- Pinning from the web page.

## Success criteria

- [x] `guild merge-queue --raid <name>` lists ready PRs in an order where PRs sharing a shared-area glob are sequential, each position with its reason.
- [x] Blocked PRs are listed with exact reasons and never appear in the order.
- [x] A pin overrides the computed order, is limited to the raid lead, the owning party or the human, and drops out when a PR merges or closes.
- [x] `guild web` shows the same queue and reasons per raid and per party outside raids.
- [x] No command in this epic writes to GitHub or merges a PR.
- [x] A PR marked `fixes-main` is position 1 of the merge queue unless a task dependency or a pin puts another PR before it.

## Security and data

Adds one `gh pr view --json files,additions,deletions,createdAt` call per open PR per sync, only for parties in a raid or holding an `area:` claim. It stores file globs already configured in the project, counts and a timestamp; no file names outside the configured globs. Pins carry PR refs and the author party only. The web section is built with `createElement` and `textContent` like the rest of the page.
