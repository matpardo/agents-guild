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
