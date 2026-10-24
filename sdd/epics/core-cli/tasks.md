---
epic: core-cli
type: tasks
title: Core CLI for coordinating parallel sessions
status: done
updated: 2026-10-24
---

# Tasks: Core CLI for coordinating parallel sessions

## T01 — Event log, projections and identity

**Depends on:** —
**Status:** [x] done — 76272fd

**What:** SQLite event log with reducers and `rebuild`; session → party binding; writes refused while unbound.

## T02 — Parties, quests, tasks, PRs, asks, notices, claims

**Depends on:** T01
**Status:** [x] done — 76272fd

**What:** the write commands, `sync --source gh`, `seed`, `export`.

## T03 — Hooks

**Depends on:** T02
**Status:** [x] done — 76272fd

**What:** `session-start`, `prompt-submit`, `pre-push`; errors contained to one visible line.

## T04 — Human board and asks views

**Depends on:** T02
**Status:** [x] done — 167005c

**What:** asks first, then notices, then one block per party with PRs nested under their tasks; colors only on a TTY.

## T05 — Agent rules as an importable GUILD.md

**Depends on:** T02
**Status:** [x] done — 3849536

**What:** rules ship with the CLI; `install.sh` links them; imported by absolute path.

## T06 — Closing a party cleans up

**Depends on:** T02
**Status:** [x] done — #10

**What:** `guild party close [<party>]` works from a terminal once the session is gone; closing marks the party's quests done, dismisses its open asks, releases its claims and lists tracked PRs still open. `guild quest done <slug>` finishes a single quest.

## T07 — Party close applies the quest done gate

**Depends on:** T06
**Status:** [x] done — #95

**What:** `guild party close` refuses while an active quest of the party has tasks not done or epic drift, listing each quest and why; `--force` closes anyway and reports every such quest as closed with unfinished work.

## T08 — Quest done refreshes the SDD snapshot

**Depends on:** T07
**Status:** [x] done — #107

**What:** `guild quest done` and `guild party close` refresh the SDD snapshot of the quest project before judging drift, once per project on close; when the refresh fails they keep the stored snapshot and say it may be stale.

## T09 — One-line help for every command

**Depends on:** T08
**Status:** [x] done — #131

**What:** every subcommand and non-obvious flag has a one-line `help=`, so `guild --help` and `guild <command> --help` replace memorizing commands; internal commands are marked as such.

## T10 — Move tasks between quests

**Depends on:** T09
**Status:** [x] done — #165

**What:** `guild task move <quest>/<tid>[,<tid>...] --to <quest>` moves queued or blocked tasks to another active quest of the same project and epic, even one owned by another party, so a backlog can be split across parallel sessions; tasks with an open PR or a live claim stay. `guild quest add --epic` accepts no `--tasks` to open an empty quest that receives them. The board offers the same move on each queued or blocked task.

## T11 — Survive a deleted working directory

**Depends on:** T10
**Status:** [x] done

**What:** when the shell's working directory was deleted (for example a merged branch's worktree removed), commands and hooks resolve the project from the nearest existing parent of the shell's `PWD` or of the hook's `cwd` instead of crashing; without `PWD` the command fails with a clear message.

## T12 — Party close refuses open asks and open pull requests

**Depends on:** T11
**Status:** [x] done

**What:** `guild party close` also refuses while the party has an open ask or an open tracked PR, listing each ask and each PR (with its unseen review comment count) together with any quest problems in one message; `--force` keeps closing anyway, dismissing the asks. The web board has no party close action.
