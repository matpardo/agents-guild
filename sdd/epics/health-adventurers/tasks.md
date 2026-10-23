---
epic: health-adventurers
type: tasks
title: Health jobs the human launches as adventurers
status: draft
updated: 2026-10-23
---

# Tasks: Health jobs the human launches as adventurers

## T01 — Health jobs config

**Depends on:** —
**Status:** [ ] pending

**What:** `health_jobs` in the project config, checked by `validate_project_config`: unique names, non-empty command, valid duration.

**Acceptance:**
- [ ] Each invalid shape fails to load with a message naming the key.

## T02 — Due jobs

**Depends on:** T01
**Status:** [ ] pending

**What:** compute due jobs on read from the last `adventurer.done` per job; `guild adventurer start --job <name>`. Depends on `adventurers` T02.

**Acceptance:**
- [ ] A job is due before its first run and after `every`, and not due after a report.

## T03 — Due jobs on the board

**Depends on:** T02
**Status:** [ ] pending

**What:** due jobs in `guild board` and the web, each with the launch command for the human.

**Acceptance:**
- [ ] The node harness covers the due rows.

## T04 — Launch a job in tmux

**Depends on:** T02
**Status:** [ ] pending

**What:** `guild adventurer launch <job>` opens a tmux window with a fresh session whose first prompt is the job's command and binds it as an adventurer on that job.

**Acceptance:**
- [ ] Only the human's command opens the window; no timer or hook calls it.

## T05 — Health jobs docs

**Depends on:** T03
**Status:** [ ] pending

**What:** `README.md` config key and commands; `GUILD.md` rule for a health adventurer.

**Acceptance:**
- [ ] The config example in `README.md` loads.
