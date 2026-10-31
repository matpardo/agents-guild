---
epic: resource-footprint
type: tasks
title: See what each project costs the machine
status: done
updated: 2026-10-04
---

# Tasks: See what each project costs the machine

## T01 — Bounded probe runner and size parsing

**Depends on:** —
**Status:** [x] done — #71

**What:** `guild/probe.py` runs a fixed argv with closed stdin in its own process group, captures stdout and stderr apart, kills the group on timeout and never raises; `guild/resources/sizes.py` parses human sizes and `du` output.

**Acceptance:**
- [x] A missing binary, a timeout, a non-zero exit and stderr text are each reported in the result, never raised.
- [x] A timeout kills the command and its children.
- [x] Decimal units, the virtual suffix, `N/A` and garbage parse to a byte count or none.

## T02 — Sample event and projections

**Depends on:** —
**Status:** [x] done — #71

**What:** A local `resources.sampled` event per project and collect, projected into `resource_samples` and `resource_machine` by an idempotent reducer, replayed by `rebuild`.

**Acceptance:**
- [x] An unattributed event stores an empty project and an unmeasured item stores null bytes.
- [x] Replaying the same event twice changes nothing and `rebuild` reproduces both tables.
- [x] Local samples never appear in the guild export.

## T03 — Worktree discovery and disk sizing

**Depends on:** T01
**Status:** [x] done — #71

**What:** `localbase.worktrees` lists a clone's worktrees; `guild/resources/disk.py` measures each with `du -s -B1 -x`, excluding worktrees nested inside it, under a per-item timeout and a whole-run deadline.

**Acceptance:**
- [x] A worktree inside a clone is excluded from the clone's size, including paths with spaces and brackets.
- [x] A vanished or prunable worktree is missing, a timed-out or deadline-skipped one is skipped, and a missing `du` is unavailable, all with null bytes.
- [x] A branch whose latest PR is merged or closed is flagged; the main checkout and detached worktrees never are.

## T04 — Claude scratchpads, transcripts and machine totals

**Depends on:** T01
**Status:** [x] done — #71

**What:** Scratchpad and transcript directories are attributed to the longest matching checkout path among all projects and measured; machine totals cover disk, memory available and the guild database with its WAL files.

**Acceptance:**
- [x] A directory of a checkout whose path is a prefix of another is attributed to the longest match, and unknown directories are ignored.
- [x] Unreadable memory information is stored as null, not as zero.

## T05 — Docker scan and attribution

**Depends on:** T01
**Status:** [x] done — #71

**What:** `guild/resources/docker.py` reads `docker system df` twice, maps each failure to a reason, and attributes containers, images and volumes to projects through compose labels, flagging orphaned, dangling and unused objects.

**Acceptance:**
- [x] Every failure maps to its reason and an empty or incomplete answer never raises.
- [x] Compose labels with commas in the config files are read correctly.
- [x] Objects of an orphaned compose project are flagged and unattributable ones go to the unattributed bucket.

## T06 — Collector and `guild resources collect`

**Depends on:** T02, T03, T04, T05
**Status:** [x] done — #71

**What:** `guild resources collect` measures first, then records every event in one write transaction, under a non-blocking lock shared through `guild/locking.py`, and prints a one-line summary.

**Acceptance:**
- [x] Nothing is written when measuring raises and no write transaction is open while measuring.
- [x] A second collect that finds the lock held prints that it is already running and exits 0.
- [x] Unavailable and skipped parts are listed in the summary and the exit code stays 0; no projects exits 1.

## T07 — Report model and `guild resources`

**Depends on:** T02
**Status:** [x] done — #71

**What:** `guild resources [--project] [--since]` builds a model with baseline and deltas, top growers, machine line and untracked growth, and renders it.

**Acceptance:**
- [x] The baseline is the latest sample at or before the window start, else the oldest, else none.
- [x] Unmeasured items show as unknown and are left out of totals and deltas.
- [x] An unknown project exits 1 and no samples prints how to collect.

## T08 — Resources timer

**Depends on:** T06
**Status:** [x] done — #71

**What:** `guild resources-timer install|uninstall|print --every` manages its own systemd units next to the sync timer, running collect at the lowest CPU and idle IO priority.

**Acceptance:**
- [x] The sync timer units are byte-identical to before.
- [x] The resources service sets `Nice=19` and `IOSchedulingClass=idle`.

## T09 — Web resources section

**Depends on:** T07
**Status:** [x] done — #71

**What:** `GET /api/resources[?project=&since=]` serves the report model and the board shows a collapsible resources section with a tooltip per category and flag.

**Acceptance:**
- [x] The endpoint returns the documented shape, rejects an unknown project or bad window with a 4xx and is absent from `/api/board`.
- [x] Every category and flag has a tooltip.

## T10 — Documentation

**Depends on:** T06, T07, T08, T09
**Status:** [x] done — #71

**What:** README section for `guild resources`, the resources timer and `/api/resources`, with the storage and personal-data additions.

**Acceptance:**
- [x] The README documents the commands, categories, attribution rules, flags, report reading, limits, cost and storage.
- [x] The SDD documents parse and agree with the spec.

## T11 — Compact the database

**Depends on:** T10
**Status:** [x] done — #177

**What:** `guild compact` backs up the database, drops repeated sync events while keeping the first and last of each run, prunes resource samples past `resource_retention_days`, and vacuums. It also has a timer and a web action.

**Acceptance:**
- [x] A rebuild after compacting yields the same projections and the same sync freshness.
- [x] The backup is written before any delete, and a failed backup deletes nothing.
- [x] Samples are kept when `resource_retention_days` is unset.

## T12 — Readers survive a long compact

**Depends on:** T11
**Status:** [x] done — #178

**What:** Schema data migrations write only when rows match, so opening the database to read takes no write lock. The web compact button always leaves its busy state and shows the result or the error.

**Acceptance:**
- [x] `db.connect` and a read succeed while another connection holds the write lock.
- [x] The compact button shows the result or the error even when the refresh fails.

## T13 — Collect from the web

**Depends on:** T12
**Status:** [x] done

**What:** A "Collect now" button next to "Compact db" posts to `POST /api/resources/collect` and runs the same function as `guild resources collect`, so a sample can be forced without waiting for the timer.

**Acceptance:**
- [x] The endpoint records the samples and returns the summary line.
- [x] The button shows the summary or the error and leaves its busy state.

## T14 — CPU load per core in the snapshot

**Depends on:** T13
**Status:** [x] done

**What:** The machine snapshot records the 1, 5 and 15 minute load and the core count at capture time. The report and the web board show the 1-minute load per core next to RAM: amber from 0.8, red from 1.5, `cpu n/a` when unmeasured.

**Acceptance:**
- [x] `guild resources collect` stores the load and the core count in the machine row; old events replay with null values.
- [x] The `machine` line and the web pill show `cpu <load>/core (load <load1> on <n> cores, 15m <load15>)`.

## T15 — Compact keeps the database bounded

**Depends on:** T11
**Status:** [x] done

**What:** `guild compact` keeps only the newest epic and tracker snapshot per key, since each one replaces the previous. Resource samples are pruned past `resource_retention_days`, 90 when absent. Per-session state files untouched for 30 days are deleted. The compaction point file holds only the latest value.

**Acceptance:**
- [x] Differing tracker snapshots leave only the newest per project; a rebuild yields the same projections and the same sync freshness.
- [x] Without configured retention, samples older than 90 days are deleted.
- [x] Stale `ctx`, `ctx-baseline` and `background` files are deleted and fresh ones kept; a dry run deletes nothing.

## T16 — Compact keeps the previous snapshot

**Depends on:** T15
**Status:** [x] done

**What:** `guild compact` keeps the two newest epic and tracker snapshots per key instead of one, so the last change stays visible after a compact.

**Acceptance:**
- [x] Several snapshots of a key leave the newest and the previous one; two snapshots are left untouched.
