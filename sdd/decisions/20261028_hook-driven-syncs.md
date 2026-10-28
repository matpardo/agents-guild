# ADR: Background jobs start from hooks and the web board, not from systemd timers

- **Date:** 2026-10-28
- **Status:** accepted

## Context

Six systemd user timers (gh, sdd, tracker and bases syncs, resources collect, compact) ran on a fixed schedule whether or not anything used guild. They needed `timers.sh`, drifted from their templates and ran on an idle machine.

## Decision

No timers. A job table (`guild/due_jobs.py`) holds each job, its interval and its priority. The session hooks (`session-start`, `prompt-submit`, `stop`), `pr wait` when it sees no sync for 30 minutes, and a ticker thread in `guild web` that checks every minute while it runs, with or without a browser open, start every due job detached. A stamp file per job under the state directory throttles them, and it is touched before the start so concurrent hooks do not start a job twice. `resources-collect` and `compact` run at `Nice=19`. `pr wait` no longer gives up with exit 4: it starts the due syncs and keeps waiting. `install.sh` removes the legacy units, and `guild doctor` warns while any remain.

## Consequences

An idle machine runs nothing. Data is as fresh as the last time a session or the board was alive, which is what the readers need. A hook adds a few stat calls and, when a job is due, one detached start.
