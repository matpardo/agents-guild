---
epic: derived-state
type: tasks
title: Flags that follow the events that resolve them
status: active
updated: 2026-10-11
---

# Tasks: Flags that follow the events that resolve them

## T01 — Derived needs-ask-answer

**Depends on:** —
**Status:** [ ] pending

**What:** a PR counts as `needs-ask-answer` while the manual flag is set or an open ask refs it (`pr:<owner/repo>#<n>`), computed at read time through one shared SQL fragment (`guild/pr_asks.py`) so nothing is stored and nothing goes stale. The merge queue, `ready-check`, the board, the web PR pill and the dispatcher promote and cap checks all read it, and name the ask: `needs ask answer (ask #N)`. `pr set --no-needs-ask-answer` clears only the manual flag; an open ask keeps blocking until it is answered or dismissed.

**Acceptance:**
- [ ] An open ask on the PR blocks it in the merge queue with `(ask #N)`; answering or dismissing it unblocks the PR with no `pr set`.
- [ ] The manual flag still blocks without an ask, and `--no-needs-ask-answer` does not hide an open ask.
- [ ] The text board and the web board model carry the ask id; the web pill names it.
- [ ] The dispatcher does not promote a PR with an open ask.

## T02 — Red-main pre-push guard

**Depends on:** —
**Status:** [ ] pending

**What:** `guild hook pre-push` refuses a push while the repo's main is red, naming the checks and since when, and the way out: fix main first, or flag the PR with `guild pr set <ref> --fixes-main`. A push from the branch of an open tracked PR flagged `fixes_main` passes; with no main status the hook stays silent. The merge queue already puts `fixes_main` PRs first and shows `MAIN RED`, and the web board already shows the main-red row; only flags backed by an event (`needs-ask-answer`) expire, no expiry is built for the other flags.

**Acceptance:**
- [ ] A push is refused while main is red, with reason and the way out.
- [ ] A push from a `fixes_main` PR branch is allowed; so is any push when main is green or unknown.
