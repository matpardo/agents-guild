# ADR: Install from a dedicated worktree

- **Date:** 2026-09-28
- **Status:** superseded by 20261008_base-clone-install

## Context

Hooks run `guild` in every session. The installed binary pointed at the development checkout, so a half-written edit went live immediately: a session hit `NameError: name 're' is not defined` from a state that never existed in any commit.

## Decision

Install from a second worktree of the same repo, pinned to a reviewed commit, and move it forward only after a merge (`checkout --detach origin/main`).

## Consequences

Development never reaches running sessions. Updating live is an explicit step after each merge.
