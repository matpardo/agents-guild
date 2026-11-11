# Development

Back to the [README](../README.md).

How guild is tested and linted, and where its specs stand. Develop in a worktree, never in the base clone (see [Install](install.md#where-to-install-from)).

- [Tests](#tests)
- [CI and dependencies](#ci-and-dependencies)
- [Lint](#lint)
- [Coverage](#coverage)
- [Status](#status)

## Tests

```
TMPDIR=/dev/shm python3 tests/run_parallel.py
```

- It runs every `tests/test_*.py` module in its own process, `--jobs` at a time (the CPU count unless given), prints the output of failing modules and a `N modules, N tests, N failed` line, and exits 1 on any failure.
- Each test builds a fresh SQLite database. `TMPDIR=/dev/shm` keeps them in memory, which avoids an `fsync` per schema statement and is several times faster than a disk-backed `/tmp`.
- A single module still runs with `python3 -m unittest tests.test_<name>`, and the serial `python3 -m unittest discover -s tests` keeps working.

## CI and dependencies

- CI (`.github/workflows/tests.yml`) runs the same command on Python 3.10 for every pull request and every push to `main`. The suite needs no global git identity: each test that commits configures its own.
- Every action in a workflow is pinned by its full commit SHA, with the release tag beside it. `tests/test_ci_pins.py` fails on a tag or branch ref.
- Dependabot (`.github/dependabot.yml`) opens a monthly pull request for a newer action or dev tool, waiting 7 days after each release. A ruff bump also needs `required-version` in `ruff.toml` raised by hand before CI passes.
- Dev tools (dev-only, never a runtime dependency) are managed with [uv](https://docs.astral.sh/uv/). `pyproject.toml` lists them in the `dev` dependency group by exact version, `uv.lock` pins the sha256 of every published file, and `required-version` in `[tool.uv]` pins uv itself (CI reads it from there).
- `uv sync --locked` builds `.venv` from the lock and fails if the lock no longer matches `pyproject.toml`. It needs neither pip nor `ensurepip`. After changing the `dev` group, run `uv lock` and commit both files.

## Lint

Ruff, configured in `ruff.toml`. CI runs the lint and the format check before the tests. `uv run ruff format .` fixes the format.

```
uv sync --locked
uv run ruff check .
uv run ruff format --check .
```

## Coverage

```
uv run coverage run -m unittest discover -s tests
uv run coverage report
```

## Releasing

Releases are semver tags `vX.Y.Z` with a GitHub Release. Cut one when something worth updating to has landed, not on every merge.

- While on `0.x`: bump the minor for a new feature or a breaking change to config, the database or hooks; bump the patch for fixes only.
- Tag merged `main` and publish:

  ```
  git fetch origin
  git tag -a vX.Y.Z -m "vX.Y.Z" origin/main
  git push origin vX.Y.Z
  gh release create vX.Y.Z --generate-notes --verify-tag
  ```

- `./update.sh` follows `main` and pulls tags with it, so between releases `guild --version` shows `vX.Y.Z-N-g<sha>`.

## Status

Every feature is specified as an epic under [`sdd/epics/`](../sdd/README.md), with its `status` in `spec.md`. Those files are the source of truth; this section only summarizes them.

- **Done:** the core CLI (identity, party, quest, task, PR, ask, notice, claim, board, brief, hooks, `gh` sync, seed, rebuild, export), `guild next`, handoff and resume, three-way tracking (SDD, tracker, guild) with `guild drift`, raids, session liveness, cost metering, merge queue, web board, lifecycle commands, resource footprint, security hardening, adventurers, solo players, realms and the rest of the epics marked `done`.
- **Active:** `install-and-update`, `party-waits`, `raids-in-practice` and `human-docs`.
- **Draft:** `agent-isolation`, `budgets`, `conflict-hotspots`, `execution-profiles`, `federation`, `message-provenance` and `skill-integration`.
- **Archived:** `dispatcher` and `officers`.

Waking an idle session from outside is a no-go, because the per-session socket is undocumented internal IPC. `guild handoff` prints the one `GUILD_RESUME=<party> claude -n <party>-g<N+1> '...'` command for a human (or an orchestrating agent) to run, and the board shows what each party waits on. Revisit auto-spawn if a public, documented session-control contract appears. The reasoning is in `sdd/decisions/20260928_idle-wake-no-go.md`.
