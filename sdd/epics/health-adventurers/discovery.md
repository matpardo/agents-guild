---
epic: health-adventurers
type: discovery
title: Health jobs the human launches as adventurers
status: done
updated: 2026-10-23
---

# Discovery: Health jobs the human launches as adventurers

## Open questions

1. Which jobs each project starts with (red main, drift, stale PRs, resources) — the dev, per project.
2. Whether `every` counts from the last report or from the last start — the dev, after the first jobs run.

## Decisions

- 2026-10-23: The human launches health jobs; guild only shows when they are due. The no-launch decision of `20261014_board-shows-waits-no-dispatcher` stays (decisión del dev).
- 2026-10-23: Guild does not depend on the repo that generates agent setups. A job names a prompt or skill as a string; the project's own setup provides it.
- 2026-10-23: This epic replaces `officers`, which was archived.
- 2026-10-23: `health_jobs` entries have exactly `name` (unique slug), `command` (non-empty string, not starting with `-`) and `every` (duration of the `--ttl` parser). A job with an active adventurer is `running`, not due; a dismissed adventurer still counts as a report (decisión del dev).
- 2026-10-23: `guild adventurer start --job <name>` takes the job name as the job text and is exclusive with a job text and `--task`; the adventurers table gets a nullable `health_job` column.
- 2026-10-23: The board model carries `health_jobs` as a flat list (project, name, state, last_done, every, launch); the CLI and web list only due and running jobs, with the launch command as copyable text and no web launch action.
- 2026-10-23: `guild adventurer launch` refuses inside a Claude Code session, opens a `health-<name>` tmux window in the first project path with `GUILD_ADVENTURER_JOB=<name> claude -n health-<name> '<command>'` (revive's quoting), and the `SessionStart` hook starts the adventurer only for `startup` sessions that are unbound, so a compaction after `done` never restarts it.
