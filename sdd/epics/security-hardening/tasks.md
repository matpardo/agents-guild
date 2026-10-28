---
epic: security-hardening
type: tasks
title: Security hardening from the internal audit
status: done
updated: 2026-09-28
---

# Tasks: Security hardening from the internal audit

## T01 — Pre-push guard fails closed

**Depends on:** —
**Status:** [x] done — #3

**What:** quote-aware tokenizer, wrappers, `bash -c`, chains; explicit warning when the branch is unknown.

## T02 — Names cannot traverse paths

**Depends on:** —
**Status:** [x] done — #3

## T03 — Strip control sequences

**Depends on:** —
**Status:** [x] done — #3

## T04 — Frame messages from other sessions as data

**Depends on:** T03
**Status:** [x] done — #3

## T05 — Personal data caps and screening

**Depends on:** —
**Status:** [x] done — #3

## T06 — Private file permissions

**Depends on:** —
**Status:** [x] done — #3

## T07 — Safe install and documented trust model

**Depends on:** —
**Status:** [x] done — #3

## T08 — Bugs found by the first real users

**Depends on:** T05
**Status:** [x] done — #3

**What:** reminder read as an error (duplicate notices); `next` crashed on PRs tracked before the migration; live install moved to a dedicated worktree.

## T09 — Ask replies refuse inside a session

**Depends on:** T04
**Status:** [x] done

**What:** The ask reply and dismiss commands refuse when the call carries a session id, so an agent cannot reply to its own ask by dodging the hook command parsing. The terminal and the web board carry no session id and keep working.

**Acceptance:**
- [x] Reply and dismiss with a session id fail and leave the ask open.
- [x] Reply and dismiss from the human terminal and the web board still work.

## T10 — Relaunch never carries bypass permissions

**Depends on:** —
**Status:** [x] done

**What:** `revive` and `handoff --respawn` pass a recorded permission mode on only when it is `default`, `acceptEdits`, `plan`, `auto` or `dontAsk`; `bypassPermissions` and unknown values are dropped.

**Acceptance:** a leader row or transcript holding `bypassPermissions` yields a relaunch command without `--permission-mode`.
