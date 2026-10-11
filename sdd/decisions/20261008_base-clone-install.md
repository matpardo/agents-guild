# ADR: Install from the base clone, develop in a temporary worktree

- **Date:** 2026-10-08
- **Status:** accepted
- **Supersedes:** 20260928_live-worktree-install

## Context

A permanent `agents-guild-live` worktree made the exception look like the normal case. Outside development one clone on `main` is enough; a second one is needed only while developing.

## Decision

The base clone `agents-guild` stays on `main` and is never edited; `~/.local/bin/guild` and `~/.claude/GUILD.md` link into it. Development happens in a `agents-guild-dev` worktree on a feature branch, created for the change and removed after the merge. The base clone's own `update.sh` (no arguments; it acts on the clone it lives in) fast-forwards the base after each merge.

## Consequences

Only merged `main` content reaches running sessions. `main` is checked out in the base, so dev worktrees always use feature branches.
