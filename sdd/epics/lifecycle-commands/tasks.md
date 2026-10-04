---
epic: lifecycle-commands
type: tasks
title: Run project commands on PR lifecycle events
status: active
updated: 2026-10-04
---

# Tasks: Run project commands on PR lifecycle events

## T01 — Lifecycle config validation

**Depends on:** —
**Status:** [ ] pending

**What:** `lifecycle` in the project config accepts `on_pr_merged` and `on_pr_closed`, each an object with a non-empty argv `command` and a required positive integer `timeout_minutes`.

**Acceptance:**
- [ ] Unknown events, string commands, bare list values, empty commands and a missing, boolean or non-positive timeout are rejected naming the key.
- [ ] A config without `lifecycle` and a valid one both load.

## T02 — Process runner and lifecycle.ran event

**Depends on:** —
**Status:** [ ] pending

**What:** `guild/lifecycle.py` runs an argv in its own session with merged output, kills the process group on timeout and returns exit code, capped sanitized output tail, timeout flag, error and duration; a local `lifecycle.ran` event with a no-op reducer.

**Acceptance:**
- [ ] Exit code, merged stderr and the end of the output are returned, stripped of control sequences.
- [ ] A timeout kills the command and its children.
- [ ] A missing executable or working directory returns an error with no exit code.
- [ ] `rebuild` replays `lifecycle.ran`.

## T03 — Lifecycle triggers in sync

**Depends on:** T01, T02
**Status:** [ ] pending

**What:** `guild sync --source gh` detects tracked, non-seeded PRs becoming merged or closed, groups them per project and event, takes the lock, runs the command from the main checkout last in the pass, records `lifecycle.ran` and posts a failure notice without output.

**Acceptance:**
- [ ] A draft PR that merges fires `on_pr_merged` once; one that closes fires `on_pr_closed`.
- [ ] PRs already merged or closed when tracked, seeded PRs and a second sync fire nothing.
- [ ] Two merges in one pass run once with two triggers; a held lock records a skipped run with no notice.
- [ ] A failing, timed-out or unlaunchable command or a missing checkout posts one notice and sync still exits 0.

## T04 — `guild lifecycle run`, docs and epic links

**Depends on:** T03
**Status:** [ ] pending

**What:** `guild lifecycle run <event> [--repo] [--dry-run]` previews or runs the declared command by hand; README section and project config entry; links from the `officers` and `dispatcher` specs.

**Acceptance:**
- [ ] `--dry-run` prints the argv, working directory and timeout and records nothing.
- [ ] A real run prints the outcome, records `lifecycle.ran` with the trigger `manual`, and fails with exit 1 on failure, timeout or error.
- [ ] An unconfigured event and several clones without `--repo` are rejected.
