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
**Status:** [x] done — #8

**What:** fill the empty tracker slot from the synced card of the task's key. Uses the tracker's status category (`done` / `indeterminate` / `new`) rather than a configured list of status names: it is tracker data, language-independent, and needs no default. On real data (826 tasks) the tracker decides 644 and surfaces 92 disagreements with SDD.

## T04 — guild drift

**Depends on:** T03
**Status:** [x] done — #9

**What:** `guild drift [--epic <slug>]`, read-only, eight rules: merged PR with task not done; tracker and SDD disagree; SDD task without card (keyed epics only); card not under its epic; PR open with card not started; PR closed unmerged; party with no running leader (`awaiting-leader` excluded); epic done (`sdd.epic_status_field`, stored as `epics.sdd_status`) with open work. Never calls `gh`/`acli`.

## T05 — Raids

**Depends on:** —
**Status:** [ ] pending

**What:** `raid join|leave` with TTL; notices `--to raid:<name>`.

## T06 — Asks ordered by what they unblock today

**Depends on:** T04
**Status:** [ ] pending

**What:** count only refs still blocked at render time.

## T07 — Drift defaults to work in progress

**Depends on:** T04
**Status:** [x] done — #11

**What:** without flags, `guild drift` scopes epic-scoped rules to epics referenced by an active quest and PR rules to PRs tracked by an active or awaiting-leader party; `--all` reports the whole project as before; `--epic` is unchanged and mutually exclusive with `--all`. The first output line always states the resolved scope.

## T08 — Read SDD from a git ref

**Depends on:** —
**Status:** [x] done — #11

**What:** the `sdd` config block accepts `git_repo`+`git_ref` instead of `root` (mutually exclusive, both git keys required together); `sync --source sdd` then fetches `origin`, lists and reads `tasks.md` files at that ref via `git ls-tree`/`git show`, never touching the repo's working copy, and stores each epic's `sdd_path` as `git:<ref>:<path>`.
