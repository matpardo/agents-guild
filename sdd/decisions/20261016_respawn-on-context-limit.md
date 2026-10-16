# ADR: Compaction triggers the handoff nudge, guild-launched windows respawn themselves

- **Date:** 2026-10-16
- **Status:** accepted
- **Supersedes:** the human-launch-only part of 20261012_dispatcher-suggests-human-launches and 20261014_board-shows-waits-no-dispatcher

## Context

Claude Code compacts the context far below `handoff_threshold` (at roughly 21-36% of the window), so the percentage nudge never fired and sessions kept compacting for days instead of handing off. Handing off also needed the human to run the printed command, even for a session guild itself had launched in a tmux window.

## Decision

Decisión del dev, 2026-10-16: a `SessionStart` with source `compact` resets the one-shot nudge marker and nudges right away, whatever the percentage; the percentage nudge stays. A session whose current generation runs in a window guild recorded (revive or an earlier respawn) is asked for `guild handoff --respawn`, which launches and binds the next generation in a new window and closes the old pane. Any other session gets the plain handoff nudge and the human relaunches with `guild revive`.

## Consequences

`handoff --respawn` is back, without keeper parties or Remote Control, and refuses before writing anything when the generation has no recorded window or when combined with `--close`. Nothing runs on a timer: the new session starts only because the session at its limit asked for it.

## Revisit when

- Compaction can be turned off or moved, so the percentage nudge is enough again.
- A session outside a guild-launched window needs to respawn too.
