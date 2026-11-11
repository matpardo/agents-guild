# ADR: `check` is a reserved word of `guild claim`

- **Date:** 2026-11-11
- **Status:** accepted

## Context

`guild claim <area> --ttl <dur>` takes the area as a bare positional with no subcommand keyword. A native `argparse` subparsers dispatch for `check` cannot sit next to it: subparsers greedily claim the first positional and reject anything that is not one of their declared choices, which would break plain `guild claim ci.yml --ttl 30m` (`ci.yml` is not a valid subcommand).

## Decision

The `claim` parser declares two positionals (`area` and an optional `check_area`) and an optional `--ttl`, and the handler dispatches on `area == "check"`. The legacy form keeps working unchanged. `guild claim check <area>` works, and `guild claim check --ttl ...` is rejected clearly because `check` takes no TTL.

## Consequences

`check` is a reserved word: an area literally named `check` can never be claimed or read this way. This is a deliberate, documented gap rather than an ambiguous parse.
