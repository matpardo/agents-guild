# agents-guild: rules for agents developing guild

Guild is a Python 3.10 stdlib-only CLI (`guild/`) with a browser board (`guild/web/`). Its specs live in `sdd/`; its user docs are `README.md` and `GUILD.md`.

## Where to work

- The base clone `agents-guild` stays on `main` and is never edited. Live sessions, the hooks and `guild web` run from it (ADR `sdd/decisions/20261021_worktrees-inside-base-clone.md`).
- Develop each feature branch in its own worktree inside the base clone: `git worktree add .claude/worktrees/<branch> -b <branch> origin/main`. Remove it after the merge.
- After a merge the base is updated with `./update.sh`, run from the base clone.

## Features

- Every feature works in both the CLI and the web. A web write action goes through `sendPost` in `guild/web/app.js`, which sends the `X-Guild-Token` header, and calls the same `guild/commands` function the CLI uses.
- Docs change in the same PR as the code: `README.md` for users, `GUILD.md` for the agent rules every session loads. A command or flag that changes agent behavior updates `GUILD.md`.
- Guild is local and optional. Never write a client project or a private name in code, docs, commits or PRs. Never put `guild`, `ask #N`, `notice #N`, party, raid or quest in text that leaves the local CLI (`tests/test_no_traces.py` guards the output).

## Tests

- Run all: `TMPDIR=/dev/shm python3 tests/run_parallel.py`. One module: `python3 -m unittest tests.test_<name>`.
- `tests/__init__.py` turns commit signing off for test repos.
- A change to a web filter or a render needs a behavior test in the node harness (`tests/web_drift_harness.js`, driven by `tests/test_web_drift.py`) when `node` exists. Without node those tests skip: say so in the PR.

## SDD

- Each PR adds a task to the matching epic's `sdd/epics/<epic>/tasks.md`.
- The task ships already `[x] done`, in the same single commit as the change. No PR number, no amend: only the checkbox is read. An epic with `status: done` only accepts tasks in that state (`tests/test_sdd_docs.py`).
- Take the next free `T` number after checking `main` and the open PRs: `git show origin/main:sdd/epics/<epic>/tasks.md` and `gh pr list --state open`.
- Format and frontmatter rules: `sdd/README.md`.

## Commits and PRs

- One-line conventional commits: `type: description`, English, imperative, lowercase after the type.
- Merge a PR only after its CI checks are green (`gh pr checks <n> --watch`) and the full suite passed locally.
