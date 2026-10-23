---
epic: health-adventurers
type: spec
title: Health jobs the human launches as adventurers
status: draft
owner: matpardo
created: 2026-10-23
updated: 2026-10-23
---

# Spec: Health jobs the human launches as adventurers

## Goal

Each project declares the recurring jobs that keep it healthy, and the board tells the human which one is due and how to launch it.

## Problem

Keeping a project healthy (red main, flaky tests, SDD and tracker drift, dependency updates, stale PRs) is recurring work no party owns. The `officers` epic planned it on top of the dispatcher, which retired (`20261014_board-shows-waits-no-dispatcher`). Nothing reminds the human that a check is overdue.

## Scope

- Project config `health_jobs`: a list of `{name, command, every}`. `command` is the prompt or skill the adventurer runs; `every` is a duration.
- A job is due when its last `adventurer done` is older than `every`, or it never ran. It is computed on read, like `guild/party_waits.py`.
- `guild adventurer start --job <name>` starts an adventurer for that job.
- The board and the web list due jobs with the command for the human to launch.
- `guild adventurer launch <job>`: a human command that opens a tmux window with a fresh session on that job.
- `README.md` and `GUILD.md` change with the code.

## Out of scope

- Launching anything on a timer or without a human command.
- Shipping the skills that do the jobs: they live in each project's agent setup.

## Success criteria

- [ ] An invalid `health_jobs` entry fails to load the project config.
- [ ] A job past its `every` shows as due in the CLI and the web, and stops being due after an adventurer on it reports.
- [ ] No code path launches a health job without a human command.

## Security and data

`command` is project config written by the human and is passed as the session's first prompt, never run by a shell. Pending text follows the adventurer rules.
