# ADR: Seven-day dependency cooldown

- **Date:** 2026-11-01
- **Status:** accepted

## Context

Actions and dev tools waited 14 days after a release before a bump (`20261025_dev-tools-as-uv-project.md`). Dependabot's `uv` job only accepts the uv version it bundles: with `required-version = "==0.13.0"` and Dependabot on 0.13.5, the job failed and main showed red while the tests were green. uv 0.13.5 was 10 days old.

## Decision

The cooldown drops to 7 days, decisión del dev 2026-11-01: most compromised releases are pulled within days, and the sha256 pins in `uv.lock` and the commit SHA pins of actions stay. `.github/dependabot.yml` uses `default-days: 7` for both ecosystems, and uv is pinned to `==0.13.5`.

## Consequences

A bump is allowed one week after a release instead of two, so a slower-detected compromise has less time to surface. Whenever Dependabot moves to a uv newer than `required-version`, its `uv` job fails again until uv is bumped by hand; developers upgrade their local uv with each bump.
