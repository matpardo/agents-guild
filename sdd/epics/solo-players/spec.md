---
epic: solo-players
type: spec
title: Built-in per-repo solo players
status: active
owner: matpardo
created: 2026-11-01
updated: 2026-11-01
---

# Spec: Built-in per-repo solo players

## Goal

A repo opts in to built-in fixers, one for a red main and one for Dependabot, and the board tells the human when each has work and how to launch it.

## Problem

Health jobs are free-form commands the project writes itself and the human launches by hand. A red main and a stuck Dependabot PR are the same chores in every repo, and nothing detects them as triggers.

## Scope

- Project config `solo_players`: a list of `{repo, job, name}` with `job` in `red-main` or `dependabot`; `name` is a display label.
- Triggers from stored facts: a red main that is not blocked by billing, and `dependabot_status` from `guild sync --source gh`.
- States `idle`, `due`, `running` and `cooling` computed on read, with a 1h cooldown after a report.
- `guild solo list` and `guild solo launch <owner/repo> <job>`; each player is also a derived health job.
- A `SOLO PLAYERS` section in the CLI board and the web.
- `README.md` and `GUILD.md` change with the code.

## Out of scope

- Launching a solo player on a timer (follow-up PR).
- Merging: a solo player never merges.

## Success criteria

- [x] An invalid `solo_players` entry fails to load the project config.
- [x] A red main or an unmergeable Dependabot PR makes the matching player due in the CLI and the web.
- [x] The human can launch a player from `guild solo launch`, and it refuses inside a session.
