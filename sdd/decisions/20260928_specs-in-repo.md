# ADR: Specs live in the code repo

- **Date:** 2026-09-28
- **Status:** accepted

## Context

A separate docs repo means two PRs per change and specs that lag the code: task checkboxes get updated later, by someone else, or never. Guild itself reads task status from SDD, so lagging specs directly degrade `guild next`.

## Decision

Keep agents-guild's specs in `sdd/` inside this repo. The PR that implements a task also marks it done. A test validates the frontmatter and parses every `tasks.md` with guild's own adapter.

## Consequences

One PR per change; specs and code merge together. The structure follows the separate-repo SDD pattern (epics, spec/tasks/discovery, decisions), so either layout works with guild.
