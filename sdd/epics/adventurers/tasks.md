---
epic: adventurers
type: tasks
title: Adventurers do one job and report what is pending
status: done
updated: 2026-10-24
---

# Tasks: Adventurers do one job and report what is pending

## T01 — Adventurer data

**Depends on:** —
**Status:** [x] done — #199

**What:** `adventurers` table, `adventurer.started` and `adventurer.done` events and their reducers; the row holds the SDD task (`<epic>/<tid>`) the adventurer works on; `prs.adventurer` column.

**Acceptance:**
- [x] Adventurers and the task they hold survive `guild rebuild`.

## T02 — Adventurer commands

**Depends on:** T01
**Status:** [x] done — #199

**What:** `guild adventurer start "<job>" [--task <epic>/<tid>]`, `guild adventurer done --pending "<text>"` and `guild adventurers [id]`. `start` refuses a session that leads a party (see `party-identity` T01), an unknown task, a task in an active quest, a task under a live claim and a task another adventurer holds; `party start` and `party resume` refuse an active adventurer.

**Acceptance:**
- [x] `done` without `--pending` fails; `--pending none` is accepted.
- [x] A task held by an adventurer is refused by `quest add`, `task add`, `claim` and `claim check` of every party.

## T03 — Hooks and the party-or-adventurer question

**Depends on:** T01
**Status:** [x] done — #199

**What:** the Stop hook records `session.stopped` for adventurers; the unbound hint asks the session to ask the human "party or adventurer" before working on a registered project.

**Acceptance:**
- [x] An adventurer's stop is recorded; an unbound session in a registered project sees the question once.

## T04 — What an adventurer may do

**Depends on:** T02
**Status:** [x] done — #199

**What:** `pr track` (with `--card` or its own `--task`), `notice`, `idea` and `ask` accept an adventurer and label it `adventurer <id>`; every command that needs a party (`require_binding`) refuses it with "adventurers do one job; quests and tasks belong to parties". `quest add --open` comes with `quest-board`.

**Acceptance:**
- [x] Each allowed and refused command has a test.

## T05 — Adventurers and missing reports on the board

**Depends on:** T02
**Status:** [x] done — #200

**What:** an adventurers section in `guild board` and the web with job, live or stopped, PRs and pending report, kept until `guild adventurer dismiss <id>` (web Dismiss button); a `stopped without report` flag for adventurers and for parties whose leader is gone without a handoff; `guild party close` requires `--pending`. Web writes go through `sendPost` and the same command functions.

**Acceptance:**
- [x] The node harness covers the section and the flag.
- [x] `party close` without `--pending` fails from the CLI (the web has no party close action).

## T06 — Adventurer docs

**Depends on:** T04
**Status:** [x] done — #200

**What:** `GUILD.md` rules: ask party or adventurer first, and every session that stops reports what is pending. `README.md` command reference. The first PR already ships the adventurer rules and commands; this task closes what is left.

**Acceptance:**
- [x] `tests/test_no_traces.py` covers adventurer ids and pending text.

## T07 — Binding commands ask, quest add does not

**Depends on:** T02
**Status:** [x] done — #202

**What:** `permissions.ask` holds `party start`, `party resume`, `raid join` and `adventurer start`; `quest` and `adventurer` join the allow list. `guild wire-settings` removes the retired `quest add` ask rule and `guild doctor` warns while it remains (decisión del dev, 2026-10-23).

**Acceptance:**
- [x] A wired settings file prompts for every binding command and never for `guild quest add`.

## T08 — Final report when work ends

**Depends on:** T05
**Status:** [x] done — #207

**What:** `guild party close` and `guild adventurer done` print a final report block after their result line: the PRs tracked (`<repo>#<n> | what | state`), quests with done/total tasks, linked ideas and the pending text for a party; job, task, PRs and pending for an adventurer. `GUILD.md` tells the session to end with a report to the human built from it (decisión del dev, 2026-10-23).

**Acceptance:**
- [x] `party close` lists merged and open PRs, quests and a linked idea.
- [x] `adventurer done` lists its PRs.

## T09 — Bind only for repo changes

**Depends on:** T07
**Status:** [x] done — #208

**What:** The unbound hint, `GUILD.md` and `README.md` say a session becomes a party or an adventurer only when its work will change a repo; sessions that answer questions, investigate or run commands stay unbound (decisión del dev, 2026-10-23).

**Acceptance:**
- [x] The unbound hint says to bind only when the work will change a repo.

## T10 — Sessions bind themselves with a recorded reason

**Depends on:** T09
**Status:** [x] done

**What:** `party start` and `adventurer start` need no human permission and require `--reason`, stored on the event, the party or adventurer row, the board and the web with the start time. `guild adventurer promote <party> --reason` turns the active adventurer into a party led by the same session; its PRs move to the party. `task add` and `quest add` take an optional `--reason`. `party resume` and `raid join` still raise a permission prompt (decisión del dev, 2026-10-24).

**Acceptance:**
- [x] `wire-settings` drops the retired start ask rules and keeps resume and raid join.
- [x] Both starts refuse a missing, empty or sensitive reason.
- [x] `adventurer promote` creates the party, ends the adventurer as promoted and moves its PRs.
- [x] The board and the web show reason, start time and the adventurer a party came from.

## T11 — Final reports read fresh PR states

**Depends on:** T08
**Status:** [x] done

**What:** `adventurer done` and `party close` refresh each tracked open PR from GitHub before the open-work check and the final report, so a PR merged on GitHub is reported `merged`. When GitHub cannot be reached the report keeps the last synced state and adds `(PR state as of last sync)`.

**Acceptance:**
- [x] `adventurer done` reports a PR merged on GitHub as `merged` without a prior sync.
- [x] `party close` without `--force` succeeds when the only open PR was merged on GitHub.
- [x] A GitHub failure adds the last-sync note and does not abort the command.

## T12 — Free jobs track PRs without a card

**Depends on:** T11
**Status:** [x] done

**What:** An adventurer on a free job tracks its PR without `--task`, and `--card` becomes optional, so repos without a tracker can track loose PRs. `--task` on a free job is still refused.

**Acceptance:**
- [x] A free-job adventurer tracks a PR with neither `--task` nor `--card`, and `adventurer done` reports it.
- [x] A free-job adventurer passing `--task` is refused.

## T13 — Adventurers always hold a task

**Depends on:** T12
**Status:** [x] done

**What:** `adventurer start` requires `--task` unless it starts a health job. The task is a synced SDD task, a new task the PR adds to an epic already synced, or a task of a no-epic open quest when the project has no SDD. Only health-job adventurers track PRs without `--task`.

**Acceptance:**
- [x] `adventurer start` without `--task` or `--job` is refused, naming both ways to get a task.
- [x] A new task id in a synced epic is accepted; an epic never synced is refused.
- [x] A health-job adventurer tracks a PR without `--task` and is refused with one.

## T14 — Drift flags adventurer tasks missing from the SDD

**Depends on:** T13
**Status:** [x] done

**What:** `guild drift` and the board report `adventurer task not in SDD` when an adventurer held a task of a synced epic, one of its PRs merged, and the epic has no synced task with that id. It catches a mistyped task id accepted at start.

**Acceptance:**
- [x] A merged adventurer PR whose task id is missing from the synced epic is a finding, in the default scope, with `--epic` and with `--all`.
- [x] A task present in the SDD, or a task of an open quest outside any epic, is not a finding.

## T15 — Final reports list what the session generated

**Depends on:** T14
**Status:** [x] done

**What:** The final report of `adventurer done` and `party close` keeps its current lines and adds what the session generated: asks with their state, ideas it created, open quests it added and notices still in force. `adventurer done` also warns, without refusing, when an ask is open or a PR is not merged or closed.

**Acceptance:**
- [x] Both reports list the generated asks, created ideas, open quests and notices; an idea already listed as linked is not repeated.
- [x] `adventurer done` prints `warning: left open: ...` only when an ask or a PR is still open.
