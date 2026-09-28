---
epic: three-way-tracking
type: tasks
title: Track work across guild, SDD, tracker and GitHub
status: active
updated: 2026-09-28
---

# Tasks: Track work across guild, SDD, tracker and GitHub

## T01 — Card key from a dedicated line

**Depends on:** —
**Status:** [x] done — #5

**What:** optional `key_line` regex in the `sdd` config; heading key still wins when both exist.

## T02 — Tracker adapter, read-only

**Depends on:** T01
**Status:** [x] done — #6

**What:** optional `sdd.epic_key_field` reads the epic's own card key from its `tasks.md` frontmatter into `epics.jira_key`; `sync --source tracker` (`jira-acli` adapter over `acli`) observes each card's status, status category and parent (children of an epic get `parent_key = <epic>`, everything else fetched by key gets `parent_key = NULL`); invalid keys, not-found keys and adapter failures are reported per card, non-fatal to the rest of the sync.

## T03 — Tracker opinion in the resolver

**Depends on:** T02
**Status:** [ ] pending

**What:** fill the empty tracker slot; configured done statuses; no hidden defaults.

## T04 — guild drift

**Depends on:** T03
**Status:** [ ] pending

**What:** rules: merged PR with task not done; card done vs SDD pending; SDD task without card or wrong parent; PR open with card not started; tracked PR closed unmerged; party without leader or handoff; epic done with open work.

## T05 — Raids

**Depends on:** —
**Status:** [ ] pending

**What:** `raid join|leave` with TTL; notices `--to raid:<name>`.

## T06 — Asks ordered by what they unblock today

**Depends on:** T04
**Status:** [ ] pending

**What:** count only refs still blocked at render time.
