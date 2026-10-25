---
epic: health-adventurers
type: tasks
title: Health jobs the human launches as adventurers
status: done
updated: 2026-10-23
---

# Tasks: Health jobs the human launches as adventurers

## T01 — Health jobs config

**Depends on:** —
**Status:** [x] done — #206

**What:** `health_jobs` in the project config, checked by `validate_project_config`: unique names, non-empty command, valid duration.

**Acceptance:**
- [x] Each invalid shape fails to load with a message naming the key.

## T02 — Due jobs

**Depends on:** T01
**Status:** [x] done — #206

**What:** compute due jobs on read from the last `adventurer.done` per job (a `health_job` column on `adventurers`); `guild adventurer start --job <name>`, exclusive with a job text and `--task`. Depends on `adventurers` T02.

**Acceptance:**
- [x] A job is due before its first run and after `every`, and not due after a report.

## T03 — Due jobs on the board

**Depends on:** T02
**Status:** [x] done — #206

**What:** due jobs in `guild board` and the web, each with the launch command for the human.

**Acceptance:**
- [x] The node harness covers the due rows.

## T04 — Launch a job in tmux

**Depends on:** T02
**Status:** [x] done — #206

**What:** `guild adventurer launch <job>` opens a tmux window with a fresh session whose first prompt is the job's command, with `GUILD_ADVENTURER_JOB` set; the `SessionStart` hook binds it as an adventurer on that job.

**Acceptance:**
- [x] Only the human's command opens the window; no timer or hook calls it.

## T05 — Health jobs docs

**Depends on:** T03
**Status:** [x] done — #206

**What:** `README.md` config key and commands; `GUILD.md` rule for a health adventurer.

**Acceptance:**
- [x] The config example in `README.md` loads.

## T06 — Heroes and solo players section

**Depends on:** T05
**Status:** [x] done

**What:** a health job takes an optional `hero` name; `guild board` and the web list every job in a `SOLO PLAYERS` section with its state and latest `pending:` text, and show the hero for the job's adventurer.

**Acceptance:**
- [x] A config with `hero` loads; an empty or non-string `hero` fails.
- [x] The node harness covers the solo players rows.
