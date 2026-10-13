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

## History

The `session-autopilot` epic first went the other way: sessions launched by guild would end themselves and the dispatcher would relaunch the next generation without a human.

1. 2026-10-12: the dispatcher learned to write an automatic handoff for a guild-launched session whose process and window were gone (#146).
2. 2026-10-12: a Stop hook was built to block an unattended session once and then hand it off and close its pane (#148). It depended on two facts about the installed Claude Code: that hooks see `TMUX_PANE`, and that a Stop hook's block decision is honored. Neither could be checked from inside a session, because Claude Code refuses to let a session start another session with permissions skipped. Checking them meant watching a real session in tmux.
3. Watching sessions in tmux was also what gave the developer useful feedback about how guild behaved. The autopilot removed exactly that view.
4. Decision (decisión del dev, 2026-10-12): the human launches every session in tmux, and guild only suggests. #148 was closed unmerged; the automatic handoff was removed (#149); `guild revive` learned to start handed-off parties (#150); the dispatcher stopped launching (#151); `--respawn` was kept for keeper parties only (#152); the epic was rescoped and closed (#153).

Kept from the attempt: the global dispatch pause, failed lifecycle runs in `guild history`, `guild handoff --party` and the web Hand off button, and `guild handoff --close`.

## Revisit when

- A session can be observed and tested end to end without a human watching tmux, for example a supported way to run and inspect a headless session from a test.
- Suggestions pile up faster than the human can relaunch them, or a party loses work because nobody saw its suggestion.
- Claude Code documents Stop hook behavior (`stop_hook_active` across continued turns, environment passed to hooks) well enough to rely on without a live check.

The closed PR #148 holds the full Stop hook design and its tests if this is reopened.

