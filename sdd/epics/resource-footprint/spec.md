---
epic: resource-footprint
type: spec
title: See what each project costs the machine
status: active
owner: matpardo
created: 2026-10-04
updated: 2026-10-04
---

# Spec: See what each project costs the machine

## Goal

`guild resources` shows per project how much disk the repo occupies (worktrees, Docker, Claude scratchpads and transcripts) and how it grew between snapshots, so the human notices a repo filling the machine before the disk is full, even when nobody watched live.

## Problem

Three incidents filled the disk: abandoned Docker images, worktrees of merged tasks left on disk, and a third cause nobody identified. Each was found only when the disk was full. A fixed checklist misses the next one, and guild measures nothing and keeps no history to look back at.

## Scope

- `guild resources collect` samples the machine and records `resources.sampled` local events; `guild resources-timer` installs a systemd timer that runs it periodically.
- Categories: git worktrees (nested worktrees excluded from their parent), Docker containers, images and volumes, Claude Code scratchpads and transcripts, plus machine totals (disk, memory available, Docker totals, guild database size).
- Attribution of Docker objects to a project through compose labels, with an unattributed bucket for the rest.
- `guild resources [--project] [--since]` reports totals and deltas against a baseline sample, the top growers and growth that no tracked item explains.
- Flags computed at collect time: worktrees of merged or closed PRs still on disk, orphaned compose objects, dangling and unused images.
- A web section and `GET /api/resources` built from the same model, with a tooltip for every category and flag.
- A part that cannot be measured is recorded as unavailable, never as zero, and never fails the run.

## Out of scope

- Deleting or cleaning anything: that belongs to the lifecycle commands and officers.
- Per-container or per-process memory.
- Notices, alerts and thresholds.
- Pruning or compaction of old samples.
- Per-project configuration of what to measure.

## Success criteria

- [ ] A collect without Docker records the worktrees and a Docker unavailable marker and exits 0.
- [ ] A merged worktree and orphaned compose objects are flagged.
- [ ] Two collects give deltas and top growers, and an unmeasured item shows as unknown, never as 0.
- [ ] A worktree nested inside another is not counted in its parent.
- [ ] No write lock is held while measuring, and overlapping collects do not both run.
- [ ] `guild rebuild` reproduces the projections from events.
- [ ] `/api/resources` serves the same model as the CLI and every category and flag has a tooltip.

## Security and data

Collection is read-only: nothing is deleted and nothing from a project config is executed. Every probe runs a fixed argv with no shell and a timeout. Samples hold local paths, branch names, Docker object names and byte counts; they are local events and are never exported. Nothing of a container beyond its name, size, compose project name and working directory is read or stored: no commands, environment or other labels.
