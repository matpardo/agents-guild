---
epic: solo-players
type: tasks
title: Built-in per-repo solo players
status: done
updated: 2026-11-01
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
