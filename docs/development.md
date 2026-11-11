# Development

Back to the [README](../README.md).

## Development

```
TMPDIR=/dev/shm python3 tests/run_parallel.py
```

Runs every `tests/test_*.py` module in its own process, `--jobs` at a time
(the CPU count unless given), prints the output of failing modules and a
`N modules, N tests, N failed` line, and exits 1 on any failure. Each test
builds a fresh SQLite database; `TMPDIR=/dev/shm` keeps them in memory, which
avoids an `fsync` per schema statement and is several times faster than a
disk-backed `/tmp`. A single module still runs with
`python3 -m unittest tests.test_<name>`, and the serial
`python3 -m unittest discover -s tests` keeps working.

CI (`.github/workflows/tests.yml`) runs the same command on Python 3.10
for every pull request and every push to `main`. The suite needs no global
git identity: each test that commits configures its own.
Every action in a workflow is pinned by its full commit SHA, with the
release tag beside it; `tests/test_ci_pins.py` fails on a tag or branch ref.
Dependabot (`.github/dependabot.yml`) opens a monthly pull request for a
newer action or dev tool, waiting 7 days after each release; a ruff bump also
needs `required-version` in `ruff.toml` raised by hand before CI passes.

Dev tools (dev-only, never a runtime dependency) are managed with
[uv](https://docs.astral.sh/uv/): `pyproject.toml` lists them in the `dev`
dependency group by exact version, `uv.lock` pins the sha256 of every
published file, and `required-version` in `[tool.uv]` pins uv itself (CI
reads it from there). `uv sync --locked` builds `.venv` from the lock and
fails if the lock no longer matches `pyproject.toml`; it needs neither pip
nor `ensurepip`. After changing the `dev` group, run `uv lock` and commit
both files.

Lint: ruff, configured in `ruff.toml`. CI runs the lint and the format
check before the tests; `uv run ruff format .` fixes the format.

```
uv sync --locked
uv run ruff check .
uv run ruff format --check .
```

Coverage:

```
uv run coverage run -m unittest discover -s tests
uv run coverage report
```

## Status

Phase 1 (core): identity, party/quest/task/pr/ask/notice/claim, board, brief,
inbox, statusline, `gh` sync, pre-push guard, hooks, seed/rebuild/export.

Phase 2 (keep moving, done): `sdd` adapter and `guild sync --source
sdd` (observed `epics`/`tasks`, epic-quest task validation against them),
gh sync extended with `mergeable`/review comment tracking, `guild next`
(ranked action queue, dependency resolver with guild > tracker > sdd
precedence and surfaced disagreements), task-scoped claims, ask/board
ask-summary sorting by unblock count, context-usage nudges
(`UserPromptSubmit`/`PostToolUse`), `guild handoff` and resuming a party
(including by session name from a human terminal).

Phase 3 (three-way tracking, done): card keys read from a dedicated
`key_line`, the epic key and status read from `sdd.epic_key_field` and
`sdd.epic_status_field` frontmatter, the read-only `jira-acli` tracker
adapter (`guild sync --source tracker`, observed `cards`), the resolver's
tracker opinion, the read-only `guild drift` report, asks ordered by how many
refs are still blocked right now, and `raid` (`raid join|leave`, `guild
raids`, notices scoped `--to raid:<name>`) are done.

**Idle-session wake: no-go (spike).** The design considered
having a resumed leader auto-spawn (`claude -n ...`) instead of asking a
human to run one command. Not built: the mechanism that could plausibly wake
or drive a specific Claude Code session from the outside is the per-session
socket under `~/.claude/`, which is undocumented internal IPC with a
per-session private key — not a public contract. Building against it now
would mean guild's core handoff flow depends on an implementation detail
that can change without notice. `guild handoff` instead prints the one
`GUILD_RESUME=<party> claude -n <party>-g<N+1> '...'` command for a human (or an orchestrating
agent) to run; the board shows what each party waits on and the human
runs the revive. Revisit auto-spawn if a public, documented session-control
contract appears.

**Phase 4 (lessons from the first real raid, specified under
`sdd/epics/`).** Done: `session-liveness` (every party shows whether it is
working, waiting on a permission prompt or stopped with work), `cost-metering`,
`ask-context`, `session-lifecycle` (handoff retention, respawn in guild-launched windows), `ephemeral-brief` (the task brief, `idle`/`queued` party
status, shorter sessions), `merge-queue`, `web-board`, `lifecycle-commands`,
`resource-footprint`, `security-hardening`, `derived-state` and `realms`. Open:
`install-and-update` and `raids-in-practice`. Drafts: `conflict-hotspots`,
`execution-profiles`, `budgets`, `officers`, `federation` and
`skill-integration`.
