---
epic: dispatcher
type: tasks
title: React to events without a watching session
status: active
updated: 2026-10-04
---

# Tasks: React to events without a watching session

## T01 — Dispatcher project config

**Depends on:** —
**Status:** [x] done — #77

**What:** a `dispatcher` block in the project config with `permission_mode` (`manual`, `acceptEdits` or `auto`), `max_launches_per_hour` and `rules`, validated when the config loads.

**Acceptance:**
- [x] A missing key, an extra key, `bypassPermissions`, `dontAsk`, `plan`, an unknown rule and the value `off` fail with a clear message.
- [x] A project without the block loads unchanged.

## T02 — Dispatch state

**Depends on:** —
**Status:** [x] done — #77

**What:** `dispatch.*` local events reduce to a `dispatch_decisions` projection; `dispatch_cursors` lives outside the projections so `rebuild` keeps it.

**Acceptance:**
- [x] `rebuild` reproduces the decisions and keeps the cursors.
- [x] A dry-run and a real decision on the same key coexist.

## T03 — `guild dispatch run` and `guild dispatch status`

**Depends on:** T01, T02
**Status:** [x] done — #77

**What:** a pass under a lock that reads events after a per-project cursor, ignores triggers older than one hour and prints what it did; `status` prints cursor, launches in the last hour, rules, launches in flight and recent decisions.

**Acceptance:**
- [x] The first pass on an enabled project decides nothing about earlier events.
- [x] A held lock exits cleanly without writing.
- [x] `--dry-run` leaves events and cursors unchanged.

## T04 — Launch a fresh generation with guards

**Depends on:** T03
**Status:** [x] done — #77

**What:** `guild/dispatch_launch.py` launches the next generation of a handed-off party in the `guild` tmux session through the handoff resume command with an explicit prompt, recording the intent before the launch.

**Acceptance:**
- [x] A live session, an open window, a launch in flight and a paused raid defer the trigger without consuming its key; a deferral is retried every pass and expires after 24 hours.
- [x] A party that did not hand off, a keeper, a closed party, a bad or unsafe cwd, a missing `guild` session and the hourly limit skip once with the reason recorded; all but keeper and closed post a notice.
- [x] The dispatcher never creates the tmux session.
- [x] A dry-run rule records `planned` and touches neither tmux nor notices.
- [x] A key is decided once and a dry-run decision does not block the real one.

## T05 — Rule: answered ask

**Depends on:** T04
**Status:** [x] done — #77

**What:** an answered ask on an enabled project launches the asking party with a prompt that names `ask #<id>`.

**Acceptance:**
- [x] An answered ask launches exactly one session for that party.
- [x] An ask dismissed before the pass, or a party without a project, launches nothing.
- [x] The answer text never reaches the launch command.

## T06 — Rule: failing checks

**Depends on:** T04
**Status:** [x] done — #77

**What:** `sync` records the head commit of each PR; settled failing checks on a head commit launch the PR owner with a prompt that names `<repo>#<n>`.

**Acceptance:**
- [x] One decision per failing head across passes, and a new failing head decides again.
- [x] Pending checks, seeded, merged and closed PRs and repos outside the project launch nothing.

## T07 — Bind confirmation and failures

**Depends on:** T04
**Status:** [x] done — #77

**What:** each pass confirms launches that bound and reports the ones that did not, with a project notice and `notify.command`.

**Acceptance:**
- [x] A launch that binds is recorded as bound.
- [x] A launch that does not bind within 10 minutes is reported once and its window left running.
- [x] A blocked party launches again only after a manual resume.

## T08 — `guild dispatch-timer`

**Depends on:** T03
**Status:** [x] done — #77

**What:** `guild dispatch-timer install --every <dur> | uninstall | print` renders the systemd units that run `guild dispatch run`.

**Acceptance:**
- [x] `print` renders `ExecStart=<guild> dispatch run`.

## T09 — Docs, spec and decision

**Depends on:** T05, T06, T07, T08
**Status:** [x] done — #77

**What:** README, GUILD.md, the spec and the decision describe the dispatcher.

**Acceptance:**
- [x] The README documents the config block, both commands, the guards and the `dispatch-failed` push.

## T10 — Close a guild-launched window after handoff

**Depends on:** T09
**Status:** [ ] pending

**What:** `guild handoff --close` closes the session's own pane only when its window is the one guild recorded for that generation.

**Acceptance:**
- [ ] A window that guild did not launch is never closed.

## T11 — Rule: converged and green PR

**Depends on:** T09
**Status:** [x] done — #115

**What:** a converging draft with settled green checks, mergeable and with no ask pending is marked ready with `gh pr ready` and notified; a PR that needs human review is only notified.

**Acceptance:**
- [ ] A PR that needs human review is never marked ready.

## T12 — Rule: merged PR tells the next in the queue

**Depends on:** T09
**Status:** [x] done — #113

**What:** when the head of a merge queue scope changes, the party that owns the new head is told once (notice and `notify.command`); notify only, no session is launched.

**Acceptance:**
- [x] The next party in the queue is told once per head change.

## T13 — Board and web show dispatcher launches

**Depends on:** T07
**Status:** [x] done — #114

**What:** `guild board` and `guild web` show launches in flight and recent failures.

**Acceptance:**
- [x] A launch in flight and a failed launch appear on both surfaces.

## T14 — Tell a live session when a dispatch waits on it

**Depends on:** T07
**Status:** [x] done — #102

**What:** the per-prompt inbox reports a trigger deferred because the party's own session is live.

**Acceptance:**
- [x] The owning party sees the line once; other parties, dry-run and other busy reasons see nothing.

## T15 — Rule: PR stops being mergeable

**Depends on:** T03
**Status:** [x] done — #103

**What:** the owning party is dispatched when its PR gets a merge conflict, changes requested, unresolved review threads or falls behind base.

**Acceptance:**
- [x] The trigger fires once per head commit and reason set; a changing thread count does not fire it again.

## T16 — Rule: next task wake-up

**Depends on:** T03
**Status:** [x] done — #105

**What:** a state rule that recomputes every pass and dispatches a handed-off party whose next unblocked task is ready.

**Acceptance:**
- [x] The party is launched once per task; keepers, parties that did not hand off, paused raids and tasks claimed by others launch nothing.

## T17 — Rule: resume a session after its usage limit

**Depends on:** T03
**Status:** [x] done — #116

**What:** a state rule that nudges a live session in a guild tmux window to continue once its usage limit has reset.

**Acceptance:**
- [x] A live session whose transcript ends in a usage-limit error gets `continue` once per limit hit, a minute after the reset; sessions without a recorded window, other trailing lines and dry-run send nothing.

## T18 — Rule: daily reminder to record SDD progress

**Depends on:** T03
**Status:** [x] done — #117

**What:** a notify-only state rule that reminds the owning party, once a day, to record progress in the epic `tasks.md` when a task has been in progress for over 24 hours with no SDD commit in that time.

**Acceptance:**
- [x] A long-running task on an epic quest with a stale `tasks.md` posts one notice per day; recent SDD commits, recent tasks, done tasks, non-epic quests, dry-run and an absent rule notify nothing.

## T19 — Web and board show dispatcher rules, deferred and recent decisions

**Depends on:** T13
**Status:** [x] done — #121

**What:** the board and web dispatcher section also list each project's rules with their mode and the launches of the last hour against the cap, deferred dispatches and the latest decisions of the non-launch rules, and show every failure including `pr_promote`.

**Acceptance:**
- [x] A failed `pr_promote` appears as failed; deferred dispatches and at most 10 recent decisions of the last 24 hours show, dry-run ones as planned, and empty parts are hidden.
