---
epic: three-way-tracking
type: tasks
title: Track work across guild, SDD, tracker and GitHub
status: done
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
**Status:** [x] done — #13

**What:** `guild raid join <name> --ttl <dur>` (refreshes on repeat join) / `guild raid leave <name>` for the caller's bound party; a raid exists while it has at least one active (non-expired) member, no separate create command; `guild raids` lists raids with active members and time left. `notice create --to raid:<name>` requires at least one active member; a session's inbox (`prompt-submit`/`post-tool-use`/`brief`) delivers a raid notice only to sessions whose bound party is an active member at delivery time, resolved by the single `notice.targeting` function shared with `guild board`/`guild statusline`. `party close` cascades into leaving every raid, `rebuild`-safe.

## T06 — Asks ordered by what they unblock today

**Depends on:** T04
**Status:** [x] done — #12

**What:** `guild asks` and the board summary sort open asks by how many refs
are still blocked *right now*, computed at render time: blocked count desc,
then `created_at` asc, then id asc. A `pr:` ref is blocked while the tracked
PR's lifecycle is not `merged`/`closed` (untracked counts as blocked); a
`task:` ref is blocked while the quest task's state is not `done` (unknown
counts as blocked). The board summary line adds `· blocks <n>` when `n > 0`;
`guild asks` prints `blocks: <n> of <total> refs still open`, or `blocks: 0
of <total> refs still open (may be stale)` when nothing is blocked anymore.

## T07 — Drift defaults to work in progress

**Depends on:** T04
**Status:** [x] done — #11

**What:** without flags, `guild drift` scopes epic-scoped rules to epics referenced by an active quest and PR rules to PRs tracked by an active or awaiting-leader party; `--all` reports the whole project as before; `--epic` is unchanged and mutually exclusive with `--all`. The first output line always states the resolved scope.

## T08 — Read SDD from a git ref

**Depends on:** —
**Status:** [x] done — #11

**What:** the `sdd` config block accepts `git_repo`+`git_ref` instead of `root` (mutually exclusive, both git keys required together); `sync --source sdd` then fetches `origin`, lists and reads `tasks.md` files at that ref via `git ls-tree`/`git show`, never touching the repo's working copy, and stores each epic's `sdd_path` as `git:<ref>:<path>`.

## T09 — Drift flags cards that lag behind guild and GitHub

**Depends on:** T04
**Status:** [x] done — #98

**What:** two drift rules, `task started, card not started` (quest task `active` whose SDD card has `status_category == new`) and `PR merged, card not done`; `PR open, card not started` and the new merged rule also honor PRs tracked with `--card`. Findings name the card and the move to make (In Progress / Done).

## T10 — Timers for SDD and tracker sync

**Depends on:** T08
**Status:** [x] done — #99

**What:** `guild sync-sdd-timer` and `guild sync-tracker-timer` (`install --every <dur> | uninstall | print`) manage their own systemd units running `sync --source sdd|tracker --all-projects`, which syncs every project with an `sdd`/`tracker` block and skips the others without a failure; a missing `acli` is a reported sync failure.

## T11 — Own-party drift reaches the party during work

**Depends on:** T09
**Status:** [x] done — #101

**What:** a party sees its own tracker and SDD drift without running `guild drift`: a capped `drift:` section in the session brief, an `update tracker/SDD: <finding>` item in `guild next` (after own PR attention, before the next task), a `move <KEY> to In Progress` line on `task start`, and an owner follow-up line (`move <KEY> to Done; mark <tid> done in <epic> tasks.md`) in merge notices.
