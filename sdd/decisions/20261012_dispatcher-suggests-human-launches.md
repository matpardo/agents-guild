# ADR: The dispatcher suggests a relaunch, the human launches

- **Date:** 2026-10-12
- **Status:** accepted
- **Supersedes:** 20261004_dispatcher-launches-fresh-sessions

## Context

The dispatcher started fresh `claude` sessions in tmux on its own and, for `limit_resume`, typed `continue` into a live window. That meant a timer could spend money and run code with the user's permissions without a human present, and it needed a permission-mode ceiling, an hourly cap, a launch breaker and a reconcile step to stay safe. `guild revive` now starts handed-off parties, so the human already has the command that launches them.

## Decision

No session starts or wakes on its own. The dispatcher only tells the human: a trigger on a party that handed off is recorded as `suggested`, posts one project notice `<party> ready to resume (<rule> <subject>): run guild revive --party <party>` and runs `notify.command` with the wait `ready`. A busy party (live session, open window, paused raid, paused dispatch) is still deferred and retried for 24 hours. `limit_resume` is notify only: it posts `resume <party> by hand: usage limit reset` and never types into a window. The project config keys `permission_mode` and `max_launches_per_hour` are removed and fail to load.

## Consequences

Nothing is spent or executed until the human runs `guild revive`. The launch code, the permission ceiling, the rate limit, the breaker, the reconcile pass and the in-flight state are deleted; the reducers for their old events stay so a replay of an existing database still works. `20260928_idle-wake-no-go` now holds fully: guild never writes to a live session. Two triggers for the same party suggest twice until the human revives it. A session that ends idle keeps its party out of dispatch until it is closed. Lifecycle commands stay in `sync`.
