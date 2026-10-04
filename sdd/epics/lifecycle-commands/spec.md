---
epic: lifecycle-commands
type: spec
title: Run project commands on PR lifecycle events
status: active
owner: matpardo
created: 2026-10-04
updated: 2026-10-04
---

# Spec: Run project commands on PR lifecycle events

## Goal

A project declares commands for lifecycle events, and guild launches them without an LLM from the main checkout and records the outcome. Guild never learns what the commands do.

## Problem

In a real run the disk reached 91% because every worktree with its own stack left a database, a package cache and an image behind. The project's cleaner removes only worktrees whose PR is merged or closed, never forces and skips unsaved work. It freed about 11 GB but ran only when someone remembered. Guild already detects merges deterministically.

## Scope

- A `lifecycle` project config block with `on_pr_merged` and `on_pr_closed`, each an object with `command` (argv list) and `timeout_minutes`.
- `guild sync --source gh` fires an event when a tracked, non-seeded PR is seen becoming merged or closed, never for historic PRs.
- Events seen in one pass are grouped per project and event: one run per group, from the main checkout of the first trigger's repo.
- A per-project, per-event lock; a trigger that finds it held is skipped and recorded.
- Blocking run with a mandatory timeout that kills the whole process group.
- A local `lifecycle.ran` event with status, exit code, duration and a capped output tail; a failure notice to the project without the output.
- `guild lifecycle run <event> [--repo] [--dry-run]` to run or preview the command by hand.

## Out of scope

- `on_main_red`: sync cannot tell the first observation of a red main from a new failure.
- `on_worktree_created`.
- A resource officer that watches disk and RAM (see `officers`).
- Detached runs, retries and re-running lock-skipped triggers.
- Moving the runner under the dispatcher (see `dispatcher`).

## Success criteria

- [ ] A merge runs `on_pr_merged` once from the main checkout and records `lifecycle.ran` with exit code and duration.
- [ ] Several merges in one pass run the command once, and a held lock records a skipped run.
- [ ] A failing command posts a notice without its output and does not fail sync.
- [ ] Seeded and already-merged PRs never trigger a command.

## Security and data

Only the declared argv is executed, with no shell and no interpolation of PR data. The output tail is stored locally only, capped to 2000 characters and stripped of control sequences; it never goes into a notice.
