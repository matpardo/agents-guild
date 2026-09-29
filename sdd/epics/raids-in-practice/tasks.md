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
**Status:** [ ] pending

**What:** project `shared_areas` globs and `shared_area_claim_ttl`; `guild hook pre-edit` auto-claims for the editing party and denies areas held by another party, for sessions and subagents alike.

## T02 — Merges announce themselves

**Depends on:** —
**Status:** [x] done — #22

**What:** `sync --source gh` posts one raid notice per tracked PR that became merged, with shared areas it touched.

## T03 — Membership until leave

**Depends on:** —
**Status:** [ ] pending

**What:** `raid join` takes exactly one of `--ttl` or `--until-leave`; warn once before a membership expires.

## T04 — No overlapping task lists

**Depends on:** —
**Status:** [x] done — #20

**What:** `quest add` rejects tasks in another party's active quest or task-claimed by another party; `guild claim check <area>` for orchestrators.

## T05 — Raid lead

**Depends on:** T03
**Status:** [ ] pending

**What:** `raid join --lead`, one lead per raid, shown in raids, board, web and briefs; members' new asks reach the lead's inbox.

## T06 — Notices reach /goal sessions

**Depends on:** —
**Status:** [ ] pending

**What:** confirm in the first raid that `PostToolUse` delivers notices on `/goal` continuation turns and to subagents; document it.

## T07 — Raid views and clearer project errors

**Depends on:** T05
**Status:** [ ] pending

**What:** `guild board --raid <name>`, raid filter in `guild web`; unknown-project errors list known project names.
