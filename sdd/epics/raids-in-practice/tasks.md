---
epic: raids-in-practice
type: tasks
title: Raids that protect parallel work on one epic
status: active
updated: 2026-09-29
---

# Tasks: Raids that protect parallel work on one epic

## T01 — Shared-area edit guard

**Depends on:** —
**Status:** [x] done — #21

**What:** project `shared_areas` globs and `shared_area_claim_ttl`; `guild hook pre-edit` auto-claims for the editing party and denies areas held by another party, for sessions and subagents alike.

## T02 — Merges announce themselves

**Depends on:** —
**Status:** [x] done — #22

**What:** `sync --source gh` posts one raid notice per tracked PR that became merged, with shared areas it touched.

## T03 — Membership until leave

**Depends on:** —
**Status:** [x] done — #23

**What:** `raid join` takes exactly one of `--ttl` or `--until-leave`; warn once before a membership expires.

## T04 — No overlapping task lists

**Depends on:** —
**Status:** [x] done — #20

**What:** `quest add` rejects tasks in another party's active quest or task-claimed by another party; `guild claim check <area>` for orchestrators.

## T05 — Raid lead

**Depends on:** T03
**Status:** [x] done — #24

**What:** `raid join --lead`, one lead per raid, shown in raids, board, web and briefs; members' new asks reach the lead's inbox.

## T06 — Notices reach /goal sessions

**Depends on:** —
**Status:** [x] done — #25

**What:** confirmed in the first raid: the cursors of the three `/goal` parties advanced to the latest events while they ran unattended, and only the prompt-submit/post-tool-use hooks move a cursor. No code needed.

## T07 — Raid views and clearer project errors

**Depends on:** T05
**Status:** [x] done — #24

**What:** `guild board --raid <name>`, raid filter in `guild web`; unknown-project errors list known project names.

## T08 — Commit-time guard for shared areas

**Depends on:** T01
**Status:** [x] done — #25

**What:** the first raid showed `coder` subagents writing every file through Bash, so `pre-edit` never fired and shared files went unclaimed. `guild hook pre-commit` claims the staged shared areas for the committing party, or rejects the commit naming the holder; wired per user through husky's `~/.config/husky/init.sh`, never in the project repository.

## T09 — Release shared-area claims on merge

**Depends on:** T02, T08
**Status:** [x] done — #29

**What:** `sync --source gh` releases the `area:` claims of the owning party that the merged PR's changed files match, and lists them as `Released:` in the merge notice; claims of other parties and `task:` claims stay.
