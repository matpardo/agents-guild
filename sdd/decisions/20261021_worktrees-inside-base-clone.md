# ADR: Dev worktrees live inside the base clone, one per branch

- **Date:** 2026-10-21
- **Status:** accepted
- **Supersedes:** 20261008_base-clone-install

## Context

A fixed `agents-guild-dev` sibling worktree held one branch at a time. Parallel work invented more siblings, and the project config had to list each one in `paths`.

## Decision

The base clone `agents-guild` stays on `main` and is never edited; `~/.local/bin/guild` and `~/.claude/GUILD.md` link into it. Each feature branch is developed in its own worktree at `.claude/worktrees/<branch>` inside the base clone (ignored by git), created for the change and removed after the merge. The base clone's own `update.sh` fast-forwards the base after each merge.

## Consequences

Project resolution matches any ancestor of the working directory, so the base clone path alone covers every dev worktree. Only merged `main` content reaches running sessions, because the installed links point at the base clone's files, not at a worktree.
