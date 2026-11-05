---
epic: solo-players
type: tasks
title: Built-in per-repo solo players
status: done
updated: 2026-11-02
---

# Tasks: Built-in per-repo solo players

## T01 — Config and triggers

**Depends on:** —
**Status:** [x] done

**What:** `solo_players` in the project config, the built-in jobs with their prompts, the derived health jobs, the red main trigger and the `dependabot_status` sync with the `dependabot.synced` event.

**Acceptance:**
- [x] Each invalid shape fails to load with a message naming the key.
- [x] A billing-blocked main never triggers and Dependabot facts record only when they change.

## T02 — Board and web section

**Depends on:** T01
**Status:** [x] done

**What:** a `SOLO PLAYERS` section in `guild board` and the web, with the launch command for a due or idle player.

**Acceptance:**
- [x] The CLI and the web show name, class, repo, trigger, state, last report and last pending text.

## T03 — Manual launch

**Depends on:** T01
**Status:** [x] done

**What:** `guild solo list` and `guild solo launch <owner/repo> <job>`, sharing the tmux launch of `guild adventurer launch`.

**Acceptance:**
- [x] Launch opens a `solo-` window even when the player is not due and refuses inside a session.

## T04 — Launch on trigger

**Depends on:** T03
**Status:** [x] done

**What:** `guild solo tick`, the `solo-tick` background job, the `solo.launched` event with its debounce and the launch notice.

**Acceptance:**
- [x] A due player launches once from the tick, a repeated tick inside the cooldown does nothing and the project gets a notice.

## T05 — No trigger on idle rows

**Depends on:** T02
**Status:** [x] done

**What:** the text board shows `no trigger` for a solo player without one, as the web does, instead of repeating its `idle` state.

**Acceptance:**
- [x] An idle player's board row reads `idle no trigger`.

## T06 — Hold a red-main player while its fix PR is open

**Depends on:** T02
**Status:** [x] done

**What:** a red-main player whose repo has an open PR tracked with `--fixes-main` is `fixing` and shows `fixing: waits on <ref>` on the board, `guild solo list` and the web, so the tick does not launch a second session for a main that stays red until a human merges.

**Acceptance:**
- [x] An open fixes-main PR of the repo makes the player `fixing` with the PR ref, a merged, closed, non-fixes-main or other-repo PR does not, and the tick does not launch it.

## T07 — Show a solo player as stalled when its session is gone

**Depends on:** T02
**Status:** [x] done

**What:** a solo player whose active adventurer has no live session is `stalled` instead of `running`, and its row reads `stalled: session gone, run guild adventurer dismiss <id>` on the board, `guild solo list` and the web. `guild adventurer dismiss` now also accepts an active adventurer whose session is gone, so the player becomes launchable again.

**Acceptance:**
- [x] An active adventurer with a live session is `running`, with a dead session `stalled` carrying its id, and the tick does not launch it.
- [x] Dismissing a stalled adventurer makes the player `due` again; dismissing one with a live session is refused.

## T08 — Back off a solo player when its trigger repeats

**Depends on:** T02
**Status:** [x] done

**What:** each launch records the trigger text it was made for, and a player whose trigger equals the one of its last launch waits 24h instead of 1h, so a trigger it cannot fix does not relaunch it every hour. The row reads `cooling: same trigger, retry after <time>` on the board, `guild solo list` and the web.

**Acceptance:**
- [x] The same trigger inside 24h of the last report or launch keeps the player cooling with a retry time, after 24h it is due, and a different trigger is due after 1h.
- [x] A launch recorded without a trigger replays and counts as a different trigger.

## T09 — Close a finished solo player's window before relaunching it

**Depends on:** T08
**Status:** [x] done

**What:** a finished solo session stays idle in its tmux window, and the tick skipped every player whose window existed, so it never launched again. A `due` player has no active adventurer and no launch inside the cooldown, so its window is a leftover: the tick closes it, then launches. A window that cannot be closed prints a failure line and the tick goes on.

**Acceptance:**
- [x] A `due` player with an existing window has it closed, then is launched with its event recorded.
- [x] A running player's window is untouched and nothing launches.
- [x] A window that cannot be closed prints a failure line and launches nothing.

## T10 — Add a solo players channel and run log

**Depends on:** T09
**Status:** [x] done

**What:** decisión del dev, 2026-11-02: the dev sees solo players at work through two read-only views. The channel (`solo.message` event, `solo_messages` table) holds only important messages: each launch (replacing the project notice), the finish of a solo adventurer, and what a player posts with `guild solo say`. `guild solo channel` and the board `solo_channel` key show it, and the web renders it as a feed. The run log reads the `adventurers` table: `guild solo runs`, and the last 5 runs per player in the board JSON and the web.

**Acceptance:**
- [x] `say` is refused outside a solo player session, strips control sequences and refuses empty or over-300 text.
- [x] A launch, manual or by the tick, and the done of a solo adventurer post a channel message and no notice; the done of a normal adventurer posts nothing.
- [x] The channel lists newest first with a limit, survives a rebuild, and the web renders feed and runs with text only.
- [x] Runs show running, stalled or done with duration and pending.

## T11 — Own view in the web side menu

**Depends on:** T10
**Status:** [x] done

**What:** decisión del dev, 2026-11-02: solo players leave the adventurers view and get `#solo-players` in the web side menu, labelled with the number of configured players. The channel feed always shows its heading and a "no messages yet" placeholder when empty, and the section dates use a short local format.

**Acceptance:**
- [x] The `#solo-players` view shows the solo players section and `#adventurers` does not.
- [x] The side menu lists "solo players (N)" right after adventurers.
- [x] An empty channel shows "no messages yet".
- [x] Last done, retry, run start and message times render as short local dates.

## T12 — Manual launch over a leftover window

**Depends on:** T11
**Status:** [x] done

**What:** `guild solo launch` refused with "window already exists" when a finished run left its window open. A player that is not running or stalled owns no live session, so an existing window is a leftover: the launch closes it, then launches. A running player is refused, and a stalled one is refused with the dismiss hint.

**Acceptance:**
- [x] A leftover window is closed, then the player is launched with its event recorded.
- [x] A running player is refused and its window is untouched.
- [x] A stalled player is refused with the `guild adventurer dismiss` hint.
- [x] A window that cannot be closed is an error and launches nothing.

## T13 — Launch all solo players at once

**Depends on:** T12
**Status:** [x] done

**What:** `guild solo launch --all` and `guild solo launch --project <name>` launch every configured player, of that project for the second form, that is not running or stalled, regardless of trigger. Single launch, the two bulk forms and the tick share one per-player path that checks the state, closes a leftover window and launches.

**Acceptance:**
- [x] `<repo> <job>`, `--all` and `--project` are mutually exclusive and exactly one is required; the command refuses inside a Claude Code session.
- [x] Each player prints one line: launched, skipped (running or stalled with the dismiss hint) or not launched with the error; a failure does not stop the rest.
- [x] An unknown project is an error.
- [x] Each launch posts the channel started message.

## T14 — Group solo players by project

**Depends on:** T13
**Status:** [x] done

**What:** solo players and their channel are grouped by project. Each `solo_channel` item of the board JSON carries `project`. The web side menu lists a sub-item `<project> (n)` under "solo players (N)" for each project with players; `#solo-players` renders one block per project and `#solo-players/<project>` only that block. `guild solo list` and `guild solo channel` group their output under a project header and take an optional `--project` filter; the text board groups the same way.

**Acceptance:**
- [x] Sub-items exist only for projects with at least one player and link to `#solo-players/<project>`.
- [x] The all view shows a block per project with its own channel and "no messages yet" when empty; the project view shows only its block.
- [x] `solo list --project` and `solo channel --project` filter, and an unknown project is an error.
- [x] The text board shows a project header under SOLO PLAYERS.

## T15 — Project tabs and side menu order

**Depends on:** T14
**Status:** [x] done

**What:** the web side menu orders needs you, adventurers, solo players, ideas, quest board and overview first, then the raid groups and the `parties` group (parties outside raids). The solo players item is a collapsed `<details>` whose summary links to `#solo-players` and whose body lists the project links; it opens when the hash names a project. `#solo-players` renders one tab per project; `#solo-players/<project>` selects that tab and the bare view the first project alphabetically. The panel shows the project's players and then its channel.

**Acceptance:**
- [x] The menu lists raids and then `parties` after the overview item, with no `solo` heading.
- [x] The solo players menu is collapsed by default and open on a project hash.
- [x] A tab per project with `aria-selected` on the current one; clicking a tab sets the hash.
- [x] The panel shows only the selected project, its channel after its players.

## T16 — Solo status command

**Depends on:** T15
**Status:** [x] done

**What:** `guild solo status` prints solo players with the scopes of `solo launch`: no argument for every player, `--project <name>` or `<owner/repo> <job>`. Rows are grouped by project like `guild solo list`, which stays as an alias. The single-player form adds the player's last 5 runs and last 10 channel messages.

**Acceptance:**
- [x] Each scope prints the expected rows; the player form adds runs and its own channel messages.
- [x] An unknown project or player is an error.
- [x] `guild solo list` still works.

## T17 — Stop, pause and resume solo players

**Depends on:** T16
**Status:** [x] done

**What:** `guild solo stop` and `guild solo resume` take the scopes of `solo launch` (`--all` is required for all players). Stop closes the window and dismisses the active adventurer of a running or stalled player, then pauses it; any other player is only paused. A paused player has the state `paused`, is never due, and a manual launch skips it. Resume lifts the pause. Pauses are the `solo.paused` and `solo.resumed` events.

**Acceptance:**
- [x] Stop on a running or stalled player kills its window, dismisses its adventurer, pauses it and posts to the channel; on an idle player it only pauses.
- [x] Stop and resume with no scope are an error; inside a session both are refused.
- [x] The tick and every launch form skip a paused player; the row carries the resume command.
- [x] A rebuild keeps pauses and resumes.

## T18 — Announce green Dependabot PRs

**Depends on:** T17
**Status:** [x] done

**What:** `guild sync --source gh` posts `<repo>#<n> ready to merge: <title>` in the solo players channel, as the repo's `dependabot` player, for each open Dependabot PR that is mergeable, clean and has only SUCCESS, NEUTRAL or SKIPPED checks (at least one). Once per PR: the `dependabot.announced` event, posted in the same transaction as the message. The built-in Dependabot prompt no longer posts the ready message.

**Acceptance:**
- [x] A ready PR is announced once; not mergeable, failing, pending, unknown or check-less PRs are not.
- [x] A repo without a `dependabot` player is not announced.
- [x] A rebuild keeps the announcements.

## T19 — Solo player work in the to-do lists

**Depends on:** T18
**Status:** [x] done

**What:** `dependabot.synced` carries the ready set (`dependabot_ready`). Each ready Dependabot PR is a row of READY FOR YOU (CLI board and web, unfiltered view only, counted in the `ready` badge). A solo player whose last run ended with pending work other than `none` while its trigger is active is a row of NEEDS YOU. Both clear by themselves; no nudge, no mark-done.

**Acceptance:**
- [x] Sync stores the ready set; a merged PR drops out on the next sync; an unchanged set records no event.
- [x] A rebuild replays the ready set; an event without `ready` replays as empty.
- [x] READY FOR YOU lists the solo rows after the tracked PRs and counts them; party and raid filters hide them.
- [x] NEEDS YOU shows a solo item only while the trigger is active and the pending text is not `none`.
- [x] The web renders both and counts the ready rows in the badge.

## T20 — Keep ready PRs while GitHub computes merge state

**Depends on:** T19
**Status:** [x] done

**What:** A Dependabot PR in the recorded ready set whose `mergeable` or `mergeStateStatus` reads `UNKNOWN` stays in the set; GitHub computes the merge state lazily after the base moves. The solo view, the board SOLO PLAYERS section and `solo status` list the PRs to merge under the `dependabot` player.

**Acceptance:**
- [x] A recorded ready PR with an unknown merge state stays ready.
- [x] A PR that was not ready is not added while its merge state is unknown.
- [x] A definite bad state, failing or pending checks, or a PR that left the list drops out.
- [x] The web renders a linked `<repo>#N <title>` line per PR to merge and nothing when empty.
- [x] The board and `solo status` print an indented `to merge:` line per PR.

## T21 — Drop stale dependencies in the dependabot player

**Depends on:** T20
**Status:** [x] done

**What:** The `dependabot` prompt gains a stale gate. A single-dependency PR whose target the base already pins is closed with `@dependabot close`. A multi-dependency PR never updates a stale dependency: a fix on the PR branch restores its base pin. A doubtful case is reported as needing a human.

**Acceptance:**
- [x] The prompt closes a stale single-dependency PR through `@dependabot close`.
- [x] The prompt never updates a stale dependency of a multi-dependency PR.
- [x] The PR comment carries no guild words.

## T22 — A repo skill gives the steps of a solo player's job

**Depends on:** T21
**Status:** [x] done

**What:** Each built-in prompt splits into a goal, steps and rules. When the local clone of the player's repo has `.claude/skills/<job>/SKILL.md`, the session starts with `/<job> <owner/repo>`, the skill replaces the built-in steps and the goal and rules stay. `guild solo launch` and the tick open the window in that clone, falling back to the project's first path.

**Acceptance:**
- [x] A clone with the job's skill gets `/<job> <owner/repo>`, the goal and the rules, and not the built-in steps; for both jobs.
- [x] A clone without it, or with another job's skill, gets the built-in prompt.
- [x] The window opens in the clone of the player's repo.

## T23 — Main red from the latest workflow run of the base branch

**Depends on:** T22
**Status:** [x] done

**What:** When no check run of the base branch head fails, the gh sync reads the last 30 workflow runs of the base branch and marks main red when the latest decided run of a workflow failed, timed out or failed to start. Repos whose CI on the base runs only on a schedule or by hand become visible to the `red-main` trigger.

**Acceptance:**
- [x] A failed latest run marks main red with `workflow <name> failed @ <sha7> (run <id>)`; a later green run clears it.
- [x] Runs in progress, cancelled or skipped fall back to the previous run of the workflow; Dependabot update runs never count.
- [x] Failing head checks keep their reason; a `gh run list` failure is reported and leaves the status alone.

## T24 — Close guild-launched solo and health windows after done

**Depends on:** T23
**Status:** [x] done

**What:** `guild adventurer launch` and `guild solo launch` record the tmux window id they create (`health_window.launched`, table `health_windows`). The `Stop` hook closes the pane of a session whose adventurer is done when its window is a recorded one in the `guild` tmux session; any failed check leaves it open. The built-in solo prompts end with one short `guild solo say` instead of the long final report.

**Acceptance:**
- [x] Both launch commands record the created window id; a failed launch records nothing.
- [x] The `Stop` hook kills the pane only for a done adventurer in a recorded window of the `guild` session.
- [x] An unset pane, an unrecorded or other window, an active adventurer or a failed tmux lookup leave the pane open.
- [x] The solo prompts ask for one short chat message before `adventurer done`.
