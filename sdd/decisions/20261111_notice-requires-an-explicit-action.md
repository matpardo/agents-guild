# ADR: `guild notice` requires an explicit action

- **Date:** 2026-11-11
- **Status:** accepted

## Context

The first plan's surface was `guild notice "<text>" ...` plus `guild notice close <id>`. That is ambiguous for `argparse`: a bare positional `"close"` used as notice text would collide with the `close` subcommand.

## Decision

Phase 1 always requires an explicit action: `guild notice create "<text>" ...` and `guild notice close <id>`.

## Consequences

Notice text can be any string, including `close`. Every notice command names its action.
