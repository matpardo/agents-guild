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
**Status:** [ ] pending

**What:** a `dispatcher` block in the project config with `permission_mode` (`manual`, `acceptEdits` or `auto`), `max_launches_per_hour` and `rules`, validated when the config loads.

**Acceptance:**
- [ ] A missing key, an extra key, `bypassPermissions`, `dontAsk`, `plan`, an unknown rule and the value `off` fail with a clear message.
- [ ] A project without the block loads unchanged.

## T02 — Dispatch state

**Depends on:** —
**Status:** [ ] pending

**What:** `dispatch.*` local events reduce to a `dispatch_decisions` projection; `dispatch_cursors` lives outside the projections so `rebuild` keeps it.

**Acceptance:**
- [ ] `rebuild` reproduces the decisions and keeps the cursors.
- [ ] A dry-run and a real decision on the same key coexist.

## T03 — `guild dispatch run` and `guild dispatch status`

**Depends on:** T01, T02
**Status:** [ ] pending

**What:** a pass under a lock that reads events after a per-project cursor, ignores triggers older than one hour and prints what it did; `status` prints cursor, launches in the last hour, rules, launches in flight and recent decisions.

**Acceptance:**
- [ ] The first pass on an enabled project decides nothing about earlier events.
- [ ] A held lock exits cleanly without writing.
- [ ] `--dry-run` leaves events and cursors unchanged.

## T04 — Launch a fresh generation with guards

**Depends on:** T03
**Status:** [ ] pending

**What:** `guild/dispatch_launch.py` launches the next generation of a handed-off party in the `guild` tmux session through the handoff resume command with an explicit prompt, recording the intent before the launch.

**Acceptance:**
- [ ] A live session, an open window, a launch in flight and a paused raid defer the trigger without consuming its key; a deferral is retried every pass and expires after 24 hours.
- [ ] A party that did not hand off, a keeper, a closed party, a bad or unsafe cwd, a missing `guild` session and the hourly limit skip once with the reason recorded; all but keeper and closed post a notice.
- [ ] The dispatcher never creates the tmux session.
- [ ] A dry-run rule records `planned` and touches neither tmux nor notices.
- [ ] A key is decided once and a dry-run decision does not block the real one.

## T05 — Rule: answered ask

**Depends on:** T04
**Status:** [ ] pending

**What:** an answered ask on an enabled project launches the asking party with a prompt that names `ask #<id>`.

**Acceptance:**
- [ ] An answered ask launches exactly one session for that party.
- [ ] An ask dismissed before the pass, or a party without a project, launches nothing.
- [ ] The answer text never reaches the launch command.

## T06 — Rule: failing checks

**Depends on:** T04
**Status:** [ ] pending

**What:** `sync` records the head commit of each PR; settled failing checks on a head commit launch the PR owner with a prompt that names `<repo>#<n>`.

**Acceptance:**
- [ ] One decision per failing head across passes, and a new failing head decides again.
- [ ] Pending checks, seeded, merged and closed PRs and repos outside the project launch nothing.

## T07 — Bind confirmation and failures

**Depends on:** T04
**Status:** [ ] pending

**What:** each pass confirms launches that bound and reports the ones that did not, with a project notice and `notify.command`.

**Acceptance:**
- [ ] A launch that binds is recorded as bound.
- [ ] A launch that does not bind within 10 minutes is reported once and its window left running.
- [ ] A blocked party launches again only after a manual resume.

## T08 — `guild dispatch-timer`

**Depends on:** T03
**Status:** [ ] pending

**What:** `guild dispatch-timer install --every <dur> | uninstall | print` renders the systemd units that run `guild dispatch run`.

**Acceptance:**
- [ ] `print` renders `ExecStart=<guild> dispatch run`.

## T09 — Docs, spec and decision

**Depends on:** T05, T06, T07, T08
**Status:** [ ] pending

**What:** README, GUILD.md, the spec and the decision describe the dispatcher.

**Acceptance:**
- [ ] The README documents the config block, both commands, the guards and the `dispatch-failed` push.

## T10 — Close a guild-launched window after handoff

**Depends on:** T09
**Status:** [ ] pending

**What:** `guild handoff --close` closes the session's own pane only when its window is the one guild recorded for that generation.

**Acceptance:**
- [ ] A window that guild did not launch is never closed.

## T11 — Rule: converged and green PR

**Depends on:** T09
**Status:** [ ] pending

**What:** a converging draft with settled green checks, mergeable and with no ask pending is marked ready with `gh pr ready` and notified; a PR that needs human review is only notified.

**Acceptance:**
- [ ] A PR that needs human review is never marked ready.

## T12 — Rule: merged PR tells the next in the queue

**Depends on:** T09
**Status:** [ ] pending

**What:** a merged PR tells the next PR in the merge queue to rebase.

**Acceptance:**
- [ ] The next party in the queue is told once per merged PR.

## T13 — Board and web show dispatcher launches

**Depends on:** T07
**Status:** [ ] pending

**What:** `guild board` and `guild web` show launches in flight and recent failures.

**Acceptance:**
- [ ] A launch in flight and a failed launch appear on both surfaces.
