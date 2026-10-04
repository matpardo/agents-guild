---
epic: cost-metering
type: tasks
title: Measure what each party costs
status: done
updated: 2026-10-04
---

# Tasks: Measure what each party costs

## T01 — Transcript usage reader

**Depends on:** —
**Status:** [x] done — #65

**What:** `guild/transcript_usage.py` reads complete lines of a transcript from a byte offset, dedupes streamed chunks by message id and stops before lines newer than a grace cutoff, returning the messages and the next offset.

**Acceptance:**
- [x] Chunks of one message id count once, with the highest value of each usage field.
- [x] A truncated last line is not consumed.

## T02 — Cost event and projection

**Depends on:** —
**Status:** [x] done — #65

**What:** `cost.sampled` local events, a `cost_samples` projection summed by reducer and a `transcript_cursors` table, replayed by `rebuild` without losing cursors.

**Acceptance:**
- [x] `rebuild` reproduces `cost_samples` from events.
- [x] Two events for the same key sum.

## T03 — Collector and attribution

**Depends on:** T01, T02
**Status:** [x] done — #65

**What:** `guild/cost_collect.py` scans session and subagent transcripts incrementally, maps session to party through the event log and task through `task.started` to `task.blocked`/`task.done` windows, and records one delta event per session, day, model and task.

**Acceptance:**
- [x] A second run over unchanged transcripts adds no event.
- [x] Usage appended later adds a delta event that sums with the first.
- [x] Unbound sessions are recorded with no party.

## T04 — `guild cost` command and docs

**Depends on:** T03
**Status:** [x] done — #65

**What:** `guild cost [--since] [--by session|party|model|quest|task] [--project]` collects and prints an aligned table in M tokens; README section; spec marked active.

**Acceptance:**
- [x] The totals for one session match a manual sum over its transcript.
- [x] `--by` groups by each of the five keys and `--project` filters.
