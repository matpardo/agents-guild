# ADR: Dev tools as a uv project

- **Date:** 2026-10-25
- **Status:** accepted

## Context

Ruff was installed with `pip install --require-hashes -r requirements-lint.txt` and coverage with an unpinned `pip install`. A machine whose Python ships without pip or `ensurepip` could not create the venv, so the lint had to be fetched by hand.

## Decision

The repo is a uv project with no package: `pyproject.toml` (`package = false`, `requires-python >= 3.10`) lists the dev tools by exact version in the `dev` dependency group, `uv.lock` pins every file by sha256, and `required-version` pins uv. Developers and CI run `uv sync --locked` and `uv run <tool>`; Dependabot follows the `uv` ecosystem with the same 14-day cooldown. The runtime stays stdlib-only and the tests still run with plain `python3`.

## Consequences

uv is a prerequisite for linting, not for using guild. A dev tool bump changes `pyproject.toml` and `uv.lock` together; a ruff bump still raises `required-version` in `ruff.toml` by hand. Coverage is now pinned too.
