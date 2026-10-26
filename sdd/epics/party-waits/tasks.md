---
epic: party-waits
type: tasks
title: Show what each party waits on
status: active
updated: 2026-10-25
---

# Tasks: Show what each party waits on

## T01 — Waits per party on the board

**Depends on:** —
**Status:** [x] done — #158

**What:** `guild/party_waits.py` derives each party's waits from the projections; `guild board` prints a `waits on:` line and the web board renders one pill per wait.

**Acceptance:**
- [x] Each wait kind has a test; the board and the web model carry `waits`.

## T02 — Fast board and quiet client hang-ups

**Depends on:** T01
**Status:** [x] done — #163

**What:** the unseen waits read only `ask.answered` and `notice.created` events from SQL instead of decoding every event after each cursor, and `guild web` drops a response quietly when the browser has already hung up.

**Acceptance:**
- [x] An event of another kind is never decoded by the waits.
- [x] A client that hung up prints no traceback.

## T03 — Remove pr ask-fix

**Depends on:** T01
**Status:** [x] done — #168

**What:** `guild pr ask-fix` and its `fixing` tag, `fix-requested` wait, web button and `fix_request_stale_hours` key are removed; `guild next` already sends the owner to a PR with failing checks, conflicts or review blockers. Old `pr.fix_requested` events replay as a no-op and the `fix_requested_at` column is dropped.

**Acceptance:**
- [x] No command, board field, web control or config key mentions a fix request.
- [x] An old `pr.fix_requested` event replays in `guild rebuild`.

## T04 — Commits behind base per PR

**Depends on:** T01
**Status:** [x] done

**What:** `guild sync --source gh` stores how many commits each open PR branch is behind its base (`prs.behind_by`, one compare API call per PR). The board PR line, the web PR card and `guild pr ready-check` show `N behind <base>` when it is above 0. It is display only: it is not a review reason and does not affect `guild next`, the merge queue or the waits.

**Acceptance:**
- [x] A failed compare call keeps the previous value and is reported; merged and closed PRs make no call.
- [x] The counter shows only above 0 in the board, the web card and `pr ready-check`, and changes no exit code.
- [x] An old `pr.synced` event without the field replays in `guild rebuild`.

## T05 — Local base drift per repo

**Depends on:** T04
**Status:** [x] done

**What:** Replaces T04's per-PR count. `guild sync --source gh` runs `git fetch origin <base>` in every located clone of every project and reports a failed fetch. `guild board` and the web header show, per clone, how many commits the local base branch is behind (and ahead of) `origin/<base>` and when it was last fetched. The `prs.behind_by` column and the PR `N behind <base>` display are removed.

**Acceptance:**
- [x] A sync fetch moves `origin/<base>` without touching local branches or worktrees; a failed fetch is a sync failure.
- [x] The board and the web header show behind, ahead, up to date and fetch age per clone; clones without `origin/HEAD` are skipped.
- [x] A database with `prs.behind_by` loses the column on open, and an old `pr.synced` event carrying `behind_by` replays in `guild rebuild`.

## T06 — Bases sync source and per-PR drift from local refs

**Depends on:** T05
**Status:** [x] done

**What:** `guild sync --source bases` (with `guild sync-bases-timer`) runs the per-clone `git fetch origin <base>` and nothing else; `sync --source gh` no longer fetches bases. The board PR line and the web PR card show `N behind <base>` computed at read time from local refs (`origin/<branch>` against `origin/<base>` in the located clone), only above 0; a missing ref shows nothing. Display only: it changes no reason, order or wait.

**Acceptance:**
- [x] `sync --source bases` fetches every clone, makes no GitHub call, and reports a failed fetch as a failure with a non-zero exit; `sync --source gh` leaves `origin/<base>` unchanged.
- [x] `sync-bases-timer print --every 1m` renders units that run `guild sync --source bases`, and `timers.sh` and `guild doctor` cover them.
- [x] The board text, the board model `behind` field and the web pill show the count only above 0; no stored data is added.

## T07 — Pause a base

**Depends on:** T06
**Status:** [x] done

**What:** `guild base pause <owner/repo>` and `guild base resume <owner/repo>` (and a pause or resume button per base in the web header) stop and restart the fetch of a repo's clones. `guild sync --source bases` and the post-merge fast-forward skip a paused repo. The board text and the board model `bases` entries carry `paused`, and a paused base raises no warning.

**Acceptance:**
- [x] A paused repo's `origin/<base>` does not move on `sync --source bases` and moves again after resume; double pause, resume when not paused and an unknown repo fail.
- [x] The pause is stored in `base_pauses` and replays in `guild rebuild`.
- [x] The web header renders a pause or resume button per base and the route calls the same function as the CLI.

## T08 — Park a party waiting on outside work

**Depends on:** T07
**Status:** [x] done

**What:** `guild handoff --parked "<reason>"`, `guild party park <name> --reason "<reason>"` and `guild party unpark <name>` (and Park and Unpark controls on the web party card) mark a party that waits on something outside development. A party without a live session shows `parked` with the reason, or `blocked` when its only work left is blocked tasks, instead of `idle`. The mark clears when a session resumes the party. `guild revive --list` prints the reason.

**Acceptance:**
- [x] An open ask beats `parked`, `parked` beats `queued`, `queued` beats `blocked`, and a resume or an unpark clears the mark; the mark replays in `guild rebuild`.
- [x] `handoff --parked` refuses a blank reason, `--party` and `prune`; `party park` and `unpark` refuse unknown or closed parties, a blank reason and unparking a party that is not parked.
- [x] The web sidebar and party card show the badge with the detail, and the park route calls the same function as the CLI.
