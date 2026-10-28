---
epic: install-and-update
type: tasks
title: Versioned install and self-update
status: active
updated: 2026-10-28
---

# Tasks: Versioned install and self-update

## T01 — Update script and doctor

**Depends on:** —
**Status:** [x] done — #15

**What:** `./update.sh <installed-worktree>` refuses local changes, moves the installed checkout to `origin/main`, lists the commits it brought, re-runs `install.sh` and runs `guild doctor`. `guild doctor` reports missing hooks in `~/.claude/settings.json`, a missing `~/.claude/GUILD.md` and invalid project configs, without writing anything.

## T02 — Tagged releases and guild version

**Depends on:** T01
**Status:** [x] done — #188

**What:** `v0.x.y` tags with a CHANGELOG; `guild version` shows the installed version and whether a newer release exists.

## T03 — Install script into a managed location

**Depends on:** T02
**Status:** [x] done — #188

**What:** an install script that places guild in `~/.local/share/guild/app` pinned to the latest release tag; running it again updates.

## T04 — guild self-update and new-release hint

**Depends on:** T03
**Status:** [x] done — #188

**What:** `guild self-update [--to <tag>]`, and the session-start brief mentions a newer release (checked in the background).

## T05 — The installed guild ignores the working directory

**Depends on:** T01
**Status:** [x] done — #26

**What:** `python3 -m guild` put the current directory ahead of `PYTHONPATH`, so running `guild` from inside any guild checkout (the development one included) ran that checkout's code instead of the installed one — the hole behind the earlier "edits go live" incident. `bin/guild` and the background sync spawned by `session-start` now start Python in isolated mode (`-I`) and put their own repo first explicitly.

## T06 — The CLAUDE.md hint prints only when the line is missing

**Depends on:** T01
**Status:** [x] done — #172

**What:** `install.sh`, and so every `./update.sh`, printed the hint to add `@~/.claude/GUILD.md` to `~/.claude/CLAUDE.md` even when the line was already there. It now prints only when `grep` does not find the line, following a symlinked `CLAUDE.md`.

## T07 — Doctor reports the timers and `timers.sh` keeps them current

**Depends on:** T01
**Status:** [x] done — #188

**What:** `install.sh` and `update.sh` never installed the systemd timers, so a fresh machine ran without them. `guild doctor` now warns per timer that is missing or drifted from its template (a moved `guild` path, an edited unit), keeping an installed interval as valid; `./update.sh` runs doctor, so the warning shows after each update. The new `./timers.sh` installs or refreshes the five timers (sync gh/sdd/tracker 10m, resources 2h, compact 1d), keeping the interval of any timer already installed. Nothing installs them unasked.

## T08 — Faster test suite

**Depends on:** T07
**Status:** [x] done — #191

**What:** The suite spent most of its time spawning the fake `gh` and `acli` scripts and rebuilding the argument parser on every in-process CLI call. The github and jira adapters now route their tool calls through one private runner that tests replace with the fixture logic of `tests/fake_gh.py` and `tests/fake_acli.py` in process; tests reuse one parser and skip gettext lookups. Production behavior is unchanged; the full run drops from about 4.5 minutes to about 1.5 on four cores with the same tests.

## T09 — Node-driven web tests share one process

**Depends on:** T08
**Status:** [x] done — #192

**What:** Each web behavior test started its own `node` process and slept 100 ms on timers. The drift and compact harnesses now serve scenarios over stdin, one fresh vm context each, and the tests talk to one long-lived node process per harness through `tests/node_harness.py`. Same tests and assertions; `test_web_drift` drops from about 23 s to about 4 s.

## T10 — Dev worktrees inside the base clone

**Depends on:** —
**Status:** [x] done — #194

**What:** Replace the fixed `agents-guild-dev` sibling worktree with one worktree per feature branch at `.claude/worktrees/<branch>` inside the base clone. The project config lists only the base clone in `paths`, since project resolution matches any ancestor of the working directory. ADR `20261021_worktrees-inside-base-clone` supersedes `20261008_base-clone-install`.

## T11 — Task check ships in the change's commit

**Depends on:** T10
**Status:** [x] done — #196

**What:** The SDD task of a PR lands already `[x] done — #<pr>` in the same single commit as the change: the PR is opened first, then the commit is amended with its number and force-pushed. No second commit, no follow-up PR.

## T12 — Run the test suite in CI

**Depends on:** —
**Status:** [x] done — #212

**What:** A GitHub Actions workflow runs `TMPDIR=/dev/shm python3 tests/run_parallel.py` on Python 3.10 for every pull request and every push to `main`, with node present so the web harness tests run. Tests carry their own git identity, so the suite passes on a runner with no global git config. A PR merges only once its checks are green and the local suite passed (the repository plan has no branch protection, so this is a rule, not a setting).

## T13 — Task check without the PR number

**Depends on:** T11, T12
**Status:** [x] done

**What:** The SDD task of a PR lands `[x] done` in the change's single commit, with no PR number. Only the checkbox is read, so the number cost an amend and a force-push, and with CI a second run, for text nothing parses. Tasks already marked `— #<pr>` stay as they are.

## T14 — Soft uninstall

**Depends on:** T01
**Status:** [x] done

**What:** `./uninstall.sh` undoes what `install.sh` and `timers.sh` put on the machine: the systemd timer and service units, the guild hooks and permission rules in `~/.claude/settings.json` (through the new `guild unwire-settings`, which keeps a `.bak` and leaves every other entry as it is), and the symlinks to `bin/guild` and `GUILD.md` that point at this clone. The data, config and state directories are kept unless `--purge` is passed. Lines it cannot edit safely, such as `@~/.claude/GUILD.md` in `CLAUDE.md` and a `guild hook pre-commit` line in a git or husky hook, are reported to remove by hand.

## T15 — Hook-driven background jobs

**Depends on:** T14
**Status:** [x] done

**What:** The six systemd timers and their `*-timer` commands and `timers.sh` are gone. The sync, resources-collect and compact jobs start detached, throttled by a stamp file per job, from the session hooks (`session-start`, `prompt-submit`, `stop`), from `pr wait` while it sees stale data and from a ticker in `guild web` that checks every minute while it runs, so an idle machine runs nothing. `pr wait` keeps waiting instead of exiting 4. `install.sh` removes the legacy units and `guild doctor` warns while any remain.
