---
epic: resource-footprint
type: tasks
title: See what each project costs the machine
status: active
updated: 2026-10-04
---

# Tasks: See what each project costs the machine

## T01 — Bounded probe runner and size parsing

**Depends on:** —
**Status:** [ ] pending

**What:** `guild/probe.py` runs a fixed argv with closed stdin in its own process group, captures stdout and stderr apart, kills the group on timeout and never raises; `guild/resources/sizes.py` parses human sizes and `du` output.

**Acceptance:**
- [ ] A missing binary, a timeout, a non-zero exit and stderr text are each reported in the result, never raised.
- [ ] A timeout kills the command and its children.
- [ ] Decimal units, the virtual suffix, `N/A` and garbage parse to a byte count or none.

## T02 — Sample event and projections

**Depends on:** —
**Status:** [ ] pending

**What:** A local `resources.sampled` event per project and collect, projected into `resource_samples` and `resource_machine` by an idempotent reducer, replayed by `rebuild`.

**Acceptance:**
- [ ] An unattributed event stores an empty project and an unmeasured item stores null bytes.
- [ ] Replaying the same event twice changes nothing and `rebuild` reproduces both tables.
- [ ] Local samples never appear in the guild export.

## T03 — Worktree discovery and disk sizing

**Depends on:** T01
**Status:** [ ] pending

**What:** `localbase.worktrees` lists a clone's worktrees; `guild/resources/disk.py` measures each with `du -s -B1 -x`, excluding worktrees nested inside it, under a per-item timeout and a whole-run deadline.

**Acceptance:**
- [ ] A worktree inside a clone is excluded from the clone's size, including paths with spaces and brackets.
- [ ] A vanished or prunable worktree is missing, a timed-out or deadline-skipped one is skipped, and a missing `du` is unavailable, all with null bytes.
- [ ] A branch whose latest PR is merged or closed is flagged; the main checkout and detached worktrees never are.

## T04 — Claude scratchpads, transcripts and machine totals

**Depends on:** T01
**Status:** [ ] pending

**What:** Scratchpad and transcript directories are attributed to the longest matching checkout path among all projects and measured; machine totals cover disk, memory available and the guild database with its WAL files.

**Acceptance:**
- [ ] A directory of a checkout whose path is a prefix of another is attributed to the longest match, and unknown directories are ignored.
- [ ] Unreadable memory information is stored as null, not as zero.

## T05 — Docker scan and attribution

**Depends on:** T01
**Status:** [ ] pending

**What:** `guild/resources/docker.py` reads `docker system df` twice, maps each failure to a reason, and attributes containers, images and volumes to projects through compose labels, flagging orphaned, dangling and unused objects.

**Acceptance:**
- [ ] Every failure maps to its reason and an empty or incomplete answer never raises.
- [ ] Compose labels with commas in the config files are read correctly.
- [ ] Objects of an orphaned compose project are flagged and unattributable ones go to the unattributed bucket.

## T06 — Collector and `guild resources collect`

**Depends on:** T02, T03, T04, T05
**Status:** [ ] pending

**What:** `guild resources collect` measures first, then records every event in one write transaction, under a non-blocking lock shared through `guild/locking.py`, and prints a one-line summary.

**Acceptance:**
- [ ] Nothing is written when measuring raises and no write transaction is open while measuring.
- [ ] A second collect that finds the lock held prints that it is already running and exits 0.
- [ ] Unavailable and skipped parts are listed in the summary and the exit code stays 0; no projects exits 1.

## T07 — Report model and `guild resources`

**Depends on:** T02
**Status:** [ ] pending

**What:** `guild resources [--project] [--since]` builds a model with baseline and deltas, top growers, machine line and untracked growth, and renders it.

**Acceptance:**
- [ ] The baseline is the latest sample at or before the window start, else the oldest, else none.
- [ ] Unmeasured items show as unknown and are left out of totals and deltas.
- [ ] An unknown project exits 1 and no samples prints how to collect.

## T08 — Resources timer

**Depends on:** T06
**Status:** [ ] pending

**What:** `guild resources-timer install|uninstall|print --every` manages its own systemd units next to the sync timer, running collect at the lowest CPU and idle IO priority.

**Acceptance:**
- [ ] The sync timer units are byte-identical to before.
- [ ] The resources service sets `Nice=19` and `IOSchedulingClass=idle`.

## T09 — Web resources section

**Depends on:** T07
**Status:** [ ] pending

**What:** `GET /api/resources[?project=&since=]` serves the report model and the board shows a collapsible resources section with a tooltip per category and flag.

**Acceptance:**
- [ ] The endpoint returns the documented shape, rejects an unknown project or bad window with a 4xx and is absent from `/api/board`.
- [ ] Every category and flag has a tooltip.

## T10 — Documentation

**Depends on:** T06, T07, T08, T09
**Status:** [ ] pending

**What:** README section for `guild resources`, the resources timer and `/api/resources`, with the storage and personal-data additions.

**Acceptance:**
- [ ] The README documents the commands, categories, attribution rules, flags, report reading, limits, cost and storage.
- [ ] The SDD documents parse and agree with the spec.
