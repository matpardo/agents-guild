# Commands

Back to the [README](../README.md).

Every guild command, grouped by what you want to do. `guild --help` lists every command with a one-line description. `guild <command> --help` shows its subcommands and flags.

- [Conventions](#conventions)
- [Getting started](#getting-started): `whoami`, `doctor`, `init-project`, `wire-settings`
- [Parties and sessions](#parties-and-sessions): `party`, `handoff`, `revive`, `brief`, `next`, `board`, `memory`, adventurers
- [Quests and tasks](#quests-and-tasks): `quest`, `task`, `drift`
- [PRs and merging](#prs-and-merging): `pr`, `sync`, `merge-queue`, `review-md`, `main`, `base`, lifecycle commands, waiting
- [Asks, notices and claims](#asks-notices-and-claims): `ask`, `answer`, `notice`, `claim`
- [Raids](#raids): `raid`
- [Ideas](#ideas): `idea`, `ideas`
- [Background jobs](#background-jobs): health jobs, solo players, the job table
- [Web board](#web-board): `guild web`
- [History and maintenance](#history-and-maintenance): `history`, `cost`, `compact`, `resources`, hooks, data commands

## Conventions

- Refs use three literal formats: `pr:<owner/repo>#<n>`, `task:<quest>/<tid>` and `card:<KEY>`.
- Durations are `30m`, `8h` or `3d`. Anything else is rejected.
- Commands marked "human terminal only" refuse to run inside a Claude Code session.
- Free text you pass (`--reason`, `--pending`, `--learned`, `--goal`, ideas, answers) goes through the same email, secret and project-pattern checks.
- Realm commands (`guild realm ...`) are in [Realms](realms.md).

## Getting started

### `guild --version`

Prints the installed version, from `git describe` of the clone guild runs from: `guild v0.1.0` on a release tag, `guild v0.1.0-3-g<sha>` three commits after it, a `-dirty` suffix with uncommitted changes, `unknown` outside git. The web board shows the same value next to its title (`version` in `GET /api/board`).

```
guild --version
```

### `guild whoami`

Shows the session, party and project you are bound to.

```
guild whoami
```

### `guild doctor`

Read-only checks of hooks, permission rules, `GUILD.md` and project configs.

```
guild doctor [--scan-prs]
```

- `--scan-prs`: also looks for guild traces in open PRs.
- It warns when a located local base is behind its `origin/<base>` ref, whatever `fast_forward_base` says. It never fetches, so it compares against the last fetched state.
- It warns when no clipboard tool (`wl-copy`, `xclip`, `xsel`) is found for `guild revive`.
- It shows the `session leads several parties` finding as a `warn`.

### `guild init-project`

Creates a project config from a JSON file. See [Configuration](configuration.md).

```
guild init-project <name> --config <file.json>
```

### `guild wire-settings` and `guild unwire-settings`

Merge guild hooks and permission rules into `~/.claude/settings.json`, or remove them.

```
guild wire-settings
guild unwire-settings
```

## Parties and sessions

A party is the group of work one leader session drives. A session is a party leader, an adventurer or unbound, never two. See [Concepts](concepts.md).

### `guild party`

Starts, resumes, edits, parks and closes parties.

```
guild party start <name> --reason "<why>" --goal "<what it is for>" --done-when "<condition that ends it>"
guild party resume <party> [--session <name>]
guild party set <party> [--goal "<text>"] [--done-when "<text>"]
guild party park <party> --reason "<what it waits on>"
guild party unpark <party>
guild party close [<party>] --pending "<text>" [--force]
```

- `start` raises no permission prompt. It is refused while this session leads another active party or is an active adventurer. `--reason` is stored on the event and shown on the board and the web.
- `start` takes no quest: the party is created empty and `guild quest add` binds quests to it ([decision](../sdd/decisions/20261111_party-start-takes-no-quest.md)).
- `--goal` and `--done-when` are required. The board header and the web party card show `goal:` and `done when:` (`no goal` for a party started before goals existed). The board JSON carries `goal` and `done_when`. `guild revive --list` prints `goal:`. `guild brief` and the handoff file (`## Goal`) carry them to the next session.
- While a party has a done condition, `guild task add` requires `--reason`, and the reason must say how the task serves that condition.
- `set` needs at least one of `--goal` or `--done-when` and is refused on a closed party. The web party card has an Edit goal button.
- `resume --session <name>` lets a human resume a party for an existing, never-bound session, found through `~/.claude/sessions` by its `/rename` name. It is refused inside a Claude Code session and fails clearly when the name is not found.
- Plain `resume <party>` prints the previous generation's handoff plus one read-only, non-acknowledging `guild next` line. The next `SessionStart` (for example after `/clear`) shows them once more, then goes back to the normal brief.
- `park` and `unpark` are for a human terminal or the web (Park and Unpark buttons). The mark clears when a session resumes the party.
- A party with no live session whose only work left is blocked tasks shows `blocked`, with the blocked count per reason.

**Closing a party.** `party close` closes your own party. From a terminal, `party close <party>` closes any party.

- `--pending "<text>"` is required: what is left (`none` when nothing is). It is stored on the `party.closed` event. The web board has no party close action.
- It applies the `guild quest done` gate to each active quest: it refuses, listing every quest with tasks not done or epic drift. It also refuses while the party has an open ask or an open tracked PR (shown with its unseen review comment count). One message lists every problem.
- `--force` closes anyway: quests are reported as `closed with unfinished work`, asks are dismissed and PRs are listed as still open.
- Before judging drift it refreshes the SDD snapshot once per project with an `sdd` block, as `guild sync --source sdd` would.
- Closing unbinds the session and a closed party cannot be resumed. It cascades in one event: active quests become `done`, open asks are dismissed, claims are released and raid memberships end. Tracked PRs stay tracked for history. Answer asks and merge or close PRs first.
- It reports `pruned N handoff file(s)` when N is above zero (see `guild handoff prune`).
- After the close line it prints a final report block from existing state:
  - each tracked PR as `<repo>#<n> | what | state` (`merged`, `closed` or `open`), refreshed from GitHub first; if that fails the report keeps the last synced states and says so;
  - each quest with done/total tasks, and the ideas linked to the party;
  - what the party generated: its asks (`ask #<n> (<state>): <question>`), ideas it created and did not link (`idea #<n> created: <title>`), open quests its leaders added (`open quest <slug>: no party yet | taken by <party>`, or `quest <slug> done`) and notices still in force (`notice #<n> (until <time>): <text>`);
  - the pending text last.
- The session ends with a report to the human built from it.
- Closed parties leave the board. Their `done` quests leave the default scope of `guild drift`.

### `guild handoff`

Writes the state a fresh session needs, so a party can continue in a new generation.

```
guild handoff --in-flight "..." --learned "..." [--parked "<what it waits on>"] [--model <m>] [--respawn] [--close]
guild handoff prune [--dry-run]
guild handoff --party <name>
```

- `--in-flight` and `--learned` are required and non-empty. The command renders `$XDG_DATA_HOME/guild/handoffs/<party>-g<N>.md` from the database: active quests, the full `guild next --all` queue, PRs, open asks, active notices and claims, plus the two free-text fields. It records `party.handed_off` (the party becomes `awaiting-leader`, `leaders.handoff_path` is set) and prints one command for the human:

```
GUILD_RESUME=<party> claude -n <party>-g<N+1> 'Continue the work described in the guild brief.'
```

- `--learned` also joins the party's memory (`guild memory add`), trimmed to the memory length cap. The handoff file keeps the full text.
- The new session binds itself. The `SessionStart` hook inherits `GUILD_RESUME` and, when the party is `awaiting-leader`, resumes it for the new session and injects the task brief plus the next item before the first prompt (the handoff alone when the party has no task). The prompt is a fixed, single-quoted constant, so nothing needs quoting.
- If the party is not waiting for a leader (still active, closed, unknown or an invalid name), nothing is bound and the context says `GUILD_RESUME=<party> not applied: ...`. A session that already leads that party (after `/clear`, say) is left alone.
- A plain `guild handoff` prints `guild revive --party <party>` first, then the raw `GUILD_RESUME=<party> claude ...` command for a terminal without tmux. Without tmux installed it prints only the raw command. The raw command carries `--permission-mode` from the mode guild recorded for the leader, kept current by `UserPromptSubmit`.
- A generation started by pasting the raw command adopts its window. At `SessionStart`, when no window is recorded and `$TMUX_PANE` sits in a window of the `guild` tmux session, guild records it (`leader.window_recorded`, table `leader_windows`), so `--respawn` is offered again.
- `--parked "<what it waits on>"` also marks the party as parked (waiting on something outside development, such as a legal answer). The board and the web show `parked` with the reason and age, and `guild revive --list` prints `parked: <reason>`. It cannot be combined with `--party` or `prune`.

**Respawn and close.**

- `--respawn` works only in a window guild launched (recorded by `guild revive` or an earlier respawn). Any other session gets `--respawn needs a window guild launched` before anything is written. It launches the fresh command itself in a window of the `guild` tmux session (created when absent, named after the party), records it (`leader.window_launched`) and waits up to 90 seconds for the new generation to bind, aborting early if the new window disappears or the party is gone.
- Once the new generation is bound it closes its own pane with `tmux kill-pane` (never the window), only when `$TMUX_PANE` is the window guild recorded for this generation and that window is still in the `guild` session. Otherwise it prints `close this window yourself`.
- If tmux is missing, the cwd is gone or tmux cannot create the window, it prints `respawn failed: <reason>; old session kept` plus the manual command. If the new generation does not bind in time, the old window stays and the new one keeps running. Nothing else is ever killed.
- The context nudge asks for `--respawn` when the session runs in such a window. Every other session gets the plain nudge, which says `auto-respawn off: this generation runs outside a guild tmux window` and asks for the printed `guild revive --party <party>` command. The nudge also comes right after a compaction (`SessionStart` with source `compact`), because Claude Code compacts far below `handoff_threshold`. A bound leader then also gets its task brief and party memory again, ahead of the nudge.
- `--close` writes the handoff like a plain call but closes this session's own pane instead of printing a command, under the same window conditions. Otherwise it prints `not a window guild launched, close it yourself` and closes nothing. It cannot be combined with `--respawn`.

**Handoff of a party with no leader.** `guild handoff --party <name>` is for a terminal only. It refuses inside a Claude Code session, refuses to combine with any other `handoff` flag (`prune`, `--in-flight`, `--learned`, `--model`, `--dry-run`, `--respawn`, `--close`) and names the offender. It refuses when the party still has a live leader (`run guild handoff from that session instead`).

- `In flight` is synthesized from the leader's recorded worktree: branch, count of uncommitted files and count of unpushed commits, never file names. Each falls back to `unknown` on a missing cwd, a non-git directory, no upstream or a detached HEAD.
- `Learned` is the fixed `none (automatic handoff)`, `party.handed_off` carries `auto: true`, and the party's memory is not extended.
- The web party card shows a `Hand off` button when the party is `active` and has no live leader (model key `has_live_leader`). `POST /api/parties/<name>/hand-off` (body `{}`) runs the same command as the human actor. A live leader, an unknown party or a closed party answers `422`. On success the party becomes `awaiting-leader`.

**Pruning.** A handoff is marked consumed (`leaders.handoff_consumed_at`) when the next generation binds, by the automatic resume or by `guild party resume`. `guild handoff prune` deletes files nobody needs and prints what it did (`would delete` with `--dry-run`, which changes nothing).

- The latest handoff of every open party is kept.
- A superseded handoff is deleted once consumed (superseded and unconsumed is kept). It records a local `handoff.pruned` event that clears `leaders.handoff_path`.
- A closed party's last handoff is kept until `handoff_retention_days` after the close (project config). Without that key it is kept forever and the summary says `kept N closed-party handoff(s): no handoff_retention_days configured`.
- State markers under `$XDG_STATE_HOME/guild/ctx`, `ctx-baseline` and `hints` of sessions that neither run (`~/.claude/sessions`) nor lead an open party are deleted once a day old. With no session registry nothing is deleted (`markers kept: no session registry`). Other files there, such as `human`, are kept.
- Only files under guild's handoffs and state directories are deleted. Symlinks are never followed (`skip ... symlink`) and paths outside the handoffs directory are skipped.
- Prune also runs at the end of every `sync --source gh` pass (so on each `SessionStart`) and on `party close`.

### `guild revive`

Relaunches active parties, parties that handed off (`awaiting-leader`) and stopped adventurers after a reboot, one tmux window per party or adventurer in a tmux session called `guild`.

```
guild revive                   # TTY: prompts "numbers to revive (e.g. 1,3)"; no TTY: lists and exits
guild revive --party alpha --party beta
guild revive --adventurer 3
guild revive --all
guild revive --list            # no tmux needed: one copy-paste command per party
```

It lists parties, then adventurers, with continuing numbers (party, project, quest progress, status, last activity, leader session name, cwd, permission mode, and `resume` or `fresh`) and starts the ones you pick.

- A session that is still running is skipped with `leader session is live` (party) or `session is live` (adventurer), so `--all` never starts a duplicate of a leader that runs outside tmux.
- An adventurer is listed when it is `active`, is not a health job or solo player (they have their own relaunch path) and has a transcript. It always resumes: `claude --resume <session-id> --name adventurer-<id> [--permission-mode <mode>]` in the cwd read from the transcript, in a window named `adventurer-<id>`. With no transcript, a missing cwd or an existing window it is skipped with the reason printed (`guild adventurer dismiss <id>` removes it). An adventurer id that is not active and revivable is an error, like an unknown party. With nothing to relaunch the output is `nothing to revive`.
- The web board has a `Revive all` button (two clicks: `Revive all`, then `Confirm revive all`; shown only when something is revivable) and a `Revive` button on each revivable party card and adventurer card (model key `revivable`). `POST /api/revive`, `POST /api/parties/<name>/revive` and `POST /api/adventurers/<id>/revive` (body `{}`) run the same command and answer its output as `message`; an unknown party or adventurer answers `422`.
- `resume` (the leader transcript exists under `~/.claude/projects`) runs `claude --resume <session-id> --name <party>-g<N> [--permission-mode <mode>]` in the recorded cwd. `fresh` runs the handoff resume command (`GUILD_RESUME=<party> claude -n <party>-g<N+1> ...`) from the same cwd.
- cwd and permission mode come from the leader row recorded by the `SessionStart` hook. When missing, the first lines of the transcript are read. An unknown mode is never invented.
- Only `default`, `acceptEdits`, `plan`, `auto` and `dontAsk` are carried over. `bypassPermissions` and any other value are dropped, so a relaunched session never starts with permission checks off. This also covers `guild handoff --respawn`.
- A party whose cwd no longer exists (a removed worktree) starts `fresh` from the nearest main checkout above it. With no such checkout, or with a window already in the `guild` session, the party is skipped with the reason printed.
- `--list` prints, per party, a one-liner for terminals without tmux: it sets the tab title with `printf '\033]0;<party>\007'`, then `cd <cwd> && claude --resume <id> --name <party>-g<N> ...`.
- The output ends with a short note: the sessions run in the background in the tmux session `guild` and survive closing the terminal, `tmux attach -t guild` (or `tmux switch-client -t guild` inside tmux) shows them, `Ctrl-b w` picks a window and `Ctrl-b d` leaves them running. `guild adventurer launch` ends with the same note. `/goal` and other in-session state are not restored: re-issue `/goal` where you used it.
- Without tmux installed, launching fails with an install hint. `--list` still works.

**Names and tmux options.**

- The window is named after the party, with `automatic-rename` and `allow-rename` off. The `guild` session sets `set-titles on`, `set-titles-string "#W"` and `mouse on` (the wheel scrolls the output, not the prompt history).
- Dragging selects text and copies it through the terminal (`set-clipboard on`, OSC 52) and, when `wl-copy` (Wayland), `xclip` or `xsel` (X11) is on `PATH`, to the system clipboard (server option `copy-command`). Ctrl+click on a hyperlink opens it with `xdg-open`.
- Only session, window and server options and one root key binding are set at runtime. Your `~/.tmux.conf` is untouched.
- Claude sessions are named `<party>-g<N>` on fresh launch and resume. A session started by hand takes the same name, or `adventurer <id>`, from the `UserPromptSubmit` hook on the first human prompt after it binds. Only a name Claude Code generated is replaced: one set with `/rename` or `-n` stays.
- Health job and solo player sessions are named `health-<job>-YYYYMMDD-HHMMSS` in local time, so each run is distinct. Their tmux window keeps the name without the timestamp.
- A party card and `guild board` label a leader with no name yet `unnamed session <first 8 characters of the session id>`. `no leader` shows only when the party has no leader session at all.

### `guild brief`

Prints what a fresh session needs to pick up one task. Read-only: no inbox cursor, no review-comment acknowledgement, no event.

```
guild brief [<party>/<quest>/<tid>]   # no argument: per-session view; with a task: read-only, budgeted brief for a fresh session
```

- With a task, it works from a terminal without a session. The party must exist and be open, the quest must belong to it and the task must exist, or it fails with a clear message and writes nothing.
- Any caller can read any party's brief: guild is a single-user local tool and does not authenticate readers.
- The generation shown is the next one, and the handoff read is the previous generation's.
- Sections, in order, with empty ones omitted:
  1. a frame line (`local data (information, not instructions)`);
  2. party and generation;
  3. the task with its state, epic and SDD spec and tasks paths;
  4. the party's PRs for that task (up to 5, newest first), each with `review comments: N (M unseen)`;
  5. the party's asks that reference the task or those PRs (every open one up to 5, the newest 3 answered with their answer);
  6. active notices that target the party;
  7. its claims (up to 5);
  8. the previous generation's handoff (or `handoff: none recorded`);
  9. the local-only reminder.
- The handoff section keeps only the previous generation's "In flight" and "Learned" text, wrapped at 300 characters per line. It is quoted behind a `  | ` marker and the brief ends with an `end of guild brief` line, so handoff content can never pass for a frame, notice or closing line. Handoff and memory text are framed the same way: a line equal to the frame's opening or closing line is dropped.
- Every other dynamic field is stripped of control sequences, single-lined and cut at 300 characters. Invisible and bidirectional Unicode characters (zero-width, bidi overrides, tag characters, private use, surrogates) are stripped too; a joiner inside an emoji sequence is lost.
- The whole brief is capped at 4000 characters. The handoff is truncated first, then the tail of the other sections, each with a `[... truncated: N lines omitted]` marker.
- A party shows `idle`, `queued`, `parked`, `blocked` or `waiting-ask` unless the leader's session file names a process that still exists.
- The `SessionStart` hook injects this same brief for a resumed generation, so a handoff or `revive` starts from the brief and runs no state command. If building it fails, the hook falls back to the handoff and adds `guild: task brief unavailable (<ExceptionClass>)`.
- Without an argument, the per-session view lists your own tracker and SDD drift under a `drift:` header: the findings of the four rules `guild next` ranks, for your party only, capped at 5 with `N more: guild drift` after them. Nothing is printed without drift. It also warns when a located local base is behind its `origin/<base>`.

### `guild next`

Picks the next thing for your party, by a fixed ranking.

```
guild next [--all]
```

Without `--all` it prints only the top item. With `--all` it prints the full queue and is always read-only. The ranking, evaluated in order:

1. Own PR marked `fixes-main` or `fixes-flaky`: it unblocks every party, so it comes first (`fixes a broken main — land it first`). A PR listed here is not listed again below.
2. Own PR with failing checks (not when they are all billing failures, `prs.checks_billing`), a merge conflict (`mergeable == CONFLICTING`) or unseen review comments (`review_comment_count > last_notified_comment_count`).
3. Own PR with the manual `needs-ask-answer` flag that has an ask referencing it, answered after the PR was last `pr set`. A PR blocked only by an open ask needs no step: answering the ask unblocks it.
4. Own PR `converging` with no activity for longer than the project's `next.stale_hours`. Skipped when that key is absent.
5. Own tracker or SDD drift (`PR open, card not started`, `PR merged, card not done`, `task started, card not started`, `task done, SDD not done`): one `update tracker/SDD: <finding>` line per finding, after PR attention and before the next task. It reads the database only; guild never writes to the tracker or the SDD.
6. Open-PR caps and the WIP limit:
   - When the project sets `max_open_prs_per_party` and your party already has that many open tracked PRs, no new task is offered: `wait: <n> open PRs, merge <ref> first`, naming the party's first PR in merge-queue order.
   - Then, when the project sets `max_open_prs` and all its parties together have that many, the line is `wait: <n> open PRs in project, merge <ref> first`, naming the first PR of the project-wide queue.
   - Absent keys mean no cap. Manually blocked PRs (directly or through a queue predecessor) are not counted.
   - WIP 1 (no config key): while an own Ready PR is not human-ready (its `human` state is `waiting` or `blocked`), no new task is offered: `wait: <ref> is not human-ready (<what is missing>), resolve it first`. Drafts, `converging` PRs, manually blocked PRs, PRs that only wait for the CI label (`ready (CI pending)`) and PRs in a project without `human_ready.ci_label` whose only missing item is `no checks on head` do not count. A party held this way still counts as having work (`stopped-with-work`, `queued`).
   - Whether a new task would touch files an open PR already changes is not checked: a task's files are unknown before work starts.
7. The next queued task of your active quests, ordered by `tasks.order_idx` (nulls last, then `tid`), whose dependencies (`tasks.deps`) all resolve `done`, with no open ask referencing it and not task-claimed by another party.
8. Nothing actionable: the exact blockers (pending deps and who says so, open ask ids, claim holders).

- A dependency disagreement between sources is always printed as a `disagreement: ...` line, whether or not it changed the outcome.
- When the top item is a PR chosen for new review comments, `guild next` also fires `pr.comments_acknowledged` for it, so the same comments are not reported again. `--all` never fires it.
- While a raid you belong to is paused, `next` returns `nothing actionable` plus `raid paused: <name>` (see [Pausing a raid](#pausing-a-raid)).

**How a task counts as done.** The dependency check asks, in this fixed order, the first source that has an opinion:

1. **guild**: any `quest_tasks` row for that epic and tid. `done` means done, any other state means not done.
2. **tracker**: the card whose key the task carries, from the last `guild sync --source tracker`. Status category `done` means done, `new` or `indeterminate` means not done; no key or no synced card means no opinion. The category is used instead of status names, so it works in any tracker language.
3. **sdd**: `tasks.sdd_status`.

No opinion anywhere means not done, never assumed done. When several sources have an opinion and disagree, `guild next` shows the disagreement.

### `guild board`

Prints the board in the terminal.

```
guild board [--party <name> | --raid <name>]
```

- `--raid <name>` narrows the board to that raid: its active member parties, their asks, notices scoped `raid:<name>` (not `guild` or `project:` ones, even from a member) and their claims. A raid with no active members, or an unknown name, gives `raid '<name>' has no active members`. `--raid` and `--party` are mutually exclusive.
- With `--raid`, it starts with `MAIN RED: <repo> — <reason> (<source>)` per red main and `next to merge: <ref>`. Each party block shows the same lines for its own queue.
- A `project <name>` block per project, before the party blocks, shows `open PRs: N/cap` and the cap `wait:` line when `max_open_prs` is set, one `hot file:` line per file touched by at least `max_open_prs_per_file` open PRs, one `finding class:` line per class (`(at threshold)` at or above `finding_guard_threshold`) and `sdd synced Xm ago, tracker synced Ym ago` (`never` before the first sync). Each party block shows `open PRs: N/cap` and its `wait:` line when `max_open_prs_per_party` is set.
- A party block prints `waits on:` after `status:` when its open work waits: `checks pending (N)`, `checks failing (N)`, `merge conflict`, `behind base`, `changes requested`, `N unresolved threads`, `human review`, `merge`, `green draft: mark ready`, the fix request tag, `ask #N open`, `ask #N answered`, `notice #N unread`, and `resets HH:MM` or `reset: resume by hand` when the live leader hit a usage limit. Only open PRs count and closed parties show nothing. The model key is `waits` (`kind`, `subject`, `label`).
- A party block ends with its raids (`raids: ci (5h left)`, `PAUSED` for a paused raid, and a `raid <name> PAUSED` header with `--raid`).
- `--party` and `--raid` print `PROGRESS · <done>/<total> tasks done (<pct>%)` (model key `blocked_groups` per party; totals come from `remaining`) and `TASKS PER DAY · last 15 days` (model key `daily_tasks`), described under [Web board](#web-board).
- Other sections: `NEEDS YOU`, `READY FOR YOU` (see [`guild review-md`](#guild-review-md)), `NOTICES · N active (M new)` (also with `--party` and `--raid`), and the adventurer, `HEALTH JOBS` and `SOLO PLAYERS` sections, hidden with `--party` and `--raid`.
- It also shows a local base line per clone (see [`guild base`](#guild-base)), a dim `N behind <base>` under each PR (see [`guild pr`](#guild-pr)) and the PR's full branch name. The branch comes from `pr track` and `guild sync`; a PR with no known branch shows nothing. The branch also ends its `guild merge-queue` line and shows on the web.

### `guild memory`

A party's small memory across generations.

```
guild memory add "<text>"                     # your bound party's memory; requires binding
guild memory list [--party <name>]            # read-only; no party: every known party
guild memory rm <party>/<seq>                 # bound session: only your own party; unbound (terminal or web): any party
```

`guild handoff --learned` joins the same memory. It is injected at `SessionStart` as local data, not instructions.

### Adventurers

An adventurer is one session doing one job on one project. A session that will change a repo for one PR job is an adventurer. Several PRs or quests make it a party.

```
guild adventurer start "<job>" --task <epic>/<tid> --reason "<why>"
guild adventurer start --job <name> --reason "<why>"
guild adventurer promote <party> --reason "<why>" --goal "<text>" --done-when "<text>"
guild adventurer launch <name>
guild adventurer done --pending "<text>"
guild adventurer dismiss <id>
guild adventurers [<id>]
```

- `start` registers the session. The project comes from the cwd and must be registered. It raises no permission prompt. `--reason` is required and shown on the board, in `guild adventurers <id>` and in the web with the start time.
- `start` refuses a session that leads a party or is already an adventurer. `party start` and `party resume` refuse an active adventurer.
- `--task <epic>/<tid>` ties it to one synced SDD task. It refuses an unknown task, a task in an active quest, a task under a live `task:<epic>/<tid>` claim and a task another active adventurer holds. The adventurer takes no claim: its row holds the task, and `quest add`, `task add`, `guild claim task:...` and `guild claim check task:...` treat it as taken (`held by adventurer <id>`) until it is done.
- `start --job <name>` is the same for a health job of the project config ([Health jobs](#health-jobs)). It takes the job name as the job text and refuses a job text, `--task`, or a name missing from `health_jobs`.
- `promote` makes the same session the leader of a new party when the work outgrows one job. The adventurer ends as `promoted`, its PRs move to the party and the party records where it came from. Its task does not move: the leader adds it to a quest with `guild quest add ... --tasks`. Promote is the only way a session changes identity.
- `launch` is for the human terminal only. See [Health jobs](#health-jobs).
- `done --pending "<text>"` ends it. `--pending` is required; `none` is the explicit empty report. It prints a final report block: job, task, the PRs it tracked (`<repo>#<n> | what | state`, refreshed from GitHub first), what it generated (asks, ideas, open quests, notices, in the same lines as the party report), a `warning: left open: <n> asks, <n> PRs` line when an ask is open or a PR is not merged or closed (a warning, not a refusal), and the pending text.
- `dismiss` removes a done adventurer, or an active one whose session is gone, from the board. The web Dismiss button calls the same function. It refuses any other adventurer.
- `adventurers` lists active adventurers newest first, then the ten most recent finished ones with job, task, project, state and pending report. `<id>` shows one.
- An adventurer can track its PRs (`guild pr track ... --task` equal to its own `<epic>/<tid>`, `--card <KEY>` optional; a health-job adventurer passes no `--task`; the PR records the adventurer and an empty party), post notices, add ideas and open asks (labelled `adventurer <id>`). The `Stop` hook records `session.stopped` for it like for a leader.
- Any command that needs a party (quests, tasks, handoff, claims, `next`) refuses with `adventurers do one job; quests and tasks belong to parties`. An adventurer's task is done when the SDD says so.
- `guild board` and the web list adventurers newest first in their own section: id, job, project, task, live or stopped, pending report once done, and their PRs. A done adventurer stays listed until dismissed.
- An active adventurer whose session is gone carries `stopped without report`. The same flag marks an active party whose leader session is gone without a `guild handoff` (the party is not `awaiting-leader`), in the CLI board and as a pill on the web party card.
- Adventurer ids, jobs and pending reports are local: do not copy them into PRs, commits or cards.

## Quests and tasks

A quest is a unit of work a party owns. A quest has tasks. An epic quest follows an epic of the SDD.

### `guild quest`

Adds, takes, releases and finishes quests.

```
guild quest add <slug> --title "..." --epic <slug> [--tasks T09,T07b] [--reason "<why>"]
guild quest add <slug> --title "..." --no-epic [--tasks A,B [--titles "First,Second"]]
guild quest add <slug> --title "..." --followups-of <quest> [--tasks A,B [--titles ...]]
guild quest add <slug> --open --title "..." (--epic <slug> --tasks T09 | --no-epic --tasks A,B --titles "First,Second")
guild quest take <slug>
guild quest release <slug>
guild quest board [--project <name>]
guild quest done <slug> [--accept-drift] [--force]
guild quest incomplete <slug> --reason "..."
```

- `add --epic` without `--tasks` creates an empty epic quest. `--reason` is optional on every `quest add`.
- `add --open` creates an open quest no party owns. It works with no session. `take` lets your party take an open quest of its project. `release` returns a quest with only queued tasks (no open PR or claim) to the board. `board` lists open quests and the synced SDD tasks no quest covers.
- `add --followups-of <quest>` creates a no-epic quest for extra work that belongs in its own quest. `<quest>` must exist and be owned by your party. The link is recorded in the `quest.added` payload (`followups_of`). `--tasks` and `--titles` work as with `--no-epic`. Combining it with `--epic` or `--no-epic` is rejected.
- No overlapping task lists: `add --epic <slug> --tasks T01,T02,...` rejects the whole command, writing nothing, when a listed task is in an active quest of another party for the same project and epic, or is task-claimed (`task:<epic>/<tid>`) by another party. The error lists every conflict with its holder, for example `T02 is in quest raid-wave1 of party alpha; T05 is claimed by party beta until 14:30`. Your own other quests, closed quests and expired claims never conflict. `guild seed` is exempt because it writes `quest.added` events directly.
- `done` finishes one quest without closing its party. It refuses while the quest has tasks that are not `done` (queued, active or blocked) and lists them. `--force` finishes anyway, and the achievement snapshot still records reality (`tasks_done` counts only done tasks). Quests without tasks are allowed.
- For an epic quest, `done` first refreshes the SDD snapshot of the project (as `guild sync --source sdd`, when the project has an `sdd` block). If that fails it keeps the stored snapshot and the refusal says it may be stale. It then runs the drift check ([`guild drift`](#guild-drift) rules, scoped to that epic) and refuses with the findings split into `yours:` and `other parties:` (each with its party). `--accept-drift` finishes anyway and records the findings.
- A quest whose tasks are all done but whose epic has drift shows `can't close: drift (N yours, M other parties)` on the text board and the web board. No-epic quests skip the gate.
- The `quest.done` event freezes an `achievement` snapshot (`started_at`, `done_at`, party, project, epic, title, `tasks_done`, `tasks_blocked_events`, `sdd_tids`, `epic_progress`, `jira_cards_done`, `prs_merged`, `handoffs`, `sessions`, `asks_raised`, `asks_answered`, `median_answer_seconds`, `drift`), because epic, card and task projections are replaced on every sync.
- `incomplete --reason "<text>"` records that a quest marked `done` was closed without being completed. Only the owning party can run it, only on a `done` quest, the reason is required and a quest can be marked once. It appends a local `quest.marked_incomplete` event `{slug, reason}`; events are never edited and the quests projection is untouched. `guild history` derives the flag: the quest leaves "Completed quests" and totals and appears under "Closed without completing". The event is local, so `guild export` skips it, and `guild rebuild` replays it as a no-op on the projections.

### `guild task`

Adds tasks to a quest and changes their state.

```
guild task add <quest>/<tid> --title "..." [--reason "<why>"] [--no-sdd]
guild task start <quest>/<tid> [--summary "..."]
guild task block <quest>/<tid> --reason "..."
guild task done  <quest>/<tid> [--summary "..."]
guild task move  <quest>/<tid>[,<tid>...] --to <quest>
guild task discard <quest>/<tid> --reason "..." [--force]
guild task restore <quest>/<tid>
```

- `add` works on any active quest of your own party, epic quests included. A done quest is refused (`quest '<q>' is done`). On an epic quest the same overlap check as `quest add` applies. A tid that is not in the epic's `tasks.md` yet is accepted.
- Guild stays read-only toward the SDD. For an epic quest, `task add` prints `add <tid> to <epic> tasks.md in the SDD` and `task done` prints `mark <tid> done in <epic> tasks.md in the SDD`. The agent updates `tasks.md` through the normal skills. Two `guild drift` rules catch a missed update (`quest task not in SDD`, `task done, SDD not done`) and the epic `quest done` gate refuses on them.
- `add --no-sdd` marks housekeeping work with no entry in `tasks.md` (a task that tracks a specs PR, say). It prints no hint, shows `(no sdd)` on the board and is skipped by the `quest task not in SDD` rule. It still has to be done before `quest done`.
- `start` adds a `move <KEY> to In Progress` line to its output when the task's SDD card is still `new` in the tracker.
- `move` hands queued or blocked tasks of your quest to another active quest, so a second party can work part of a backlog. The target party opens an empty quest first (`guild quest add <slug> --epic <epic> --title "..."`, no `--tasks`). An open quest is also a valid target. Both quests must be in the same project and the same epic (or both without an epic). It is refused, writing nothing, when a task is `active` or `done`, already exists in the target, has an open tracked PR, or holds an unexpired claim of your party (`guild release <area>` first). Title, state, summary and blocked reason travel with the task, and its tracked PRs are re-pointed to the target quest. The board shows a `move to` select on queued and blocked tasks.
- `discard` drops a task created by mistake without counting it as work done. Never use `done` for that.
  - The task keeps its row with state `discarded`, plus the reason, the author (the party, or `human` from the web) and the date. A discarded task is neither unfinished nor done: `quest done` and `party close` ignore it, progress totals, `guild history` and the final report leave it out, the board hides it and its tid is free again for other quests. `guild brief` lists it in a `discarded` lane.
  - It is refused for a `done` or already discarded task and for a task held by an adventurer. An `active` task, a task with an open tracked PR, or one with an unexpired claim of your party needs `--force`.
  - `start`, `block` and `done` refuse a discarded task.
  - On an epic quest it asks you to remove the task from `tasks.md`. The drift rule `discarded task in SDD` catches it if you forget.
  - The web board shows a `Discard` button (reason prompt, `force` checkbox) on unfinished tasks and a collapsed `Discarded (N)` list per quest with a `Restore` button.
- `restore` brings a discarded task back as `queued`.

### `guild drift`

Reports every disagreement between guild, SDD and the tracker that the last `guild sync --source gh|sdd|tracker` observed.

```
guild drift [--epic <slug> | --all]
```

It is read-only: no event, no `gh` or `acli` call. It reads only the projections a prior sync filled. The exit code is always 0. The last line is `N findings` or `no drift`. Fixing drift stays with humans and the normal skills.

- Default scope is work in progress. Epic rules run only on epics referenced by an `active` quest of the project. PR rules run only on PRs tracked by a party that is `active` or `awaiting-leader`.
- `party has no running leader` and `session leads several parties` are always project-wide. `adventurer task not in SDD` is project-wide too, and only `--epic` narrows it.
- `--all` reports the whole project (the audit mode). `--epic <slug>` restricts every epic rule to that epic, whatever the quest state. They are mutually exclusive.
- The first line states the scope: `scope: 2 epics in active quests (use --all for the whole project)`, `scope: no epics in active quests`, `scope: whole project` or `scope: epic <slug>`.
- Findings are grouped by rule, in this order, each naming the refs and what each source says:

| Rule | Finding when |
|---|---|
| `merged PR, task not done` | a tracked PR has lifecycle `merged` and its linked quest task state is not `done` |
| `tracker and SDD disagree` | a task has a synced card and `sdd_status`, and card done (`status_category == done`) disagrees with `sdd_status == done` |
| `SDD task without card` | the epic has a `jira_key` but the task has none (only for keyed epics) |
| `card not under its epic` | the epic has a `jira_key` and the task's synced card has `parent_key IS NULL` |
| `PR open, card not started` | a tracked PR is not merged/closed and its linked card (the task's SDD card, or the `--card` key of `pr track`) has `status_category == new`; says to move it to In Progress |
| `PR merged, card not done` | a tracked PR has lifecycle `merged` and its linked card has `status_category != done`; one finding per card, listing its merged PRs, says to move it to Done |
| `task started, card not started` | a quest task is `active` in guild and its SDD card has `status_category == new`; says to move the card to In Progress |
| `PR closed unmerged` | a tracked PR has lifecycle `closed` |
| `party has no running leader` | an `active` party's `leader_session_id` is not the id of any session file under the Claude sessions dir (`awaiting-leader` parties are not findings) |
| `session leads several parties` | one session id leads more than one `active` party of the project (a double binding from before `party start` and `party resume` refused a second party); `guild doctor` shows it as a `warn` |
| `epic done with open work` | the epic's `sdd_status == done` but it still has a non-done quest task, or an open tracked PR linked to it |
| `quest task not in SDD` | a task of an epic quest has no synced task with that tid in the epic's `tasks.md` (typically added with `guild task add` and never written to the SDD) |
| `task done, SDD not done` | a task of an epic quest is `done` in guild while the epic's synced `sdd_status` for that tid is not `done` |
| `discarded task in SDD` | a task of an epic quest was discarded in guild while the epic's `tasks.md` still lists that tid; remove it there or run `guild task restore` |
| `adventurer task not in SDD` | an adventurer held `<epic>/<tid>` of a synced epic, one of its tracked PRs is `merged`, and the epic has no synced task with that tid (a mistyped tid, or a task the PR never added to `tasks.md`); a sync of the SDD after the merge clears a correct one |

## PRs and merging

### `guild pr`

Tracks PRs and sets their state.

```
guild pr track <owner/repo>#<n> --task <quest>/<tid> [--card <KEY>] --what "..." --waits "..." [--needs-human-pr-review] [--fixes-main] [--fixes-flaky]
guild pr set   <owner/repo>#<n> [--lifecycle draft|converging|ready] [--waits "..."]
                               [--needs-ask-answer | --no-needs-ask-answer]
                               [--needs-human-pr-review | --no-needs-human-pr-review]
                               [--fixes-main | --no-fixes-main]
                               [--fixes-flaky | --no-fixes-flaky]
                               [--blocked-external "<reason>" | --no-blocked-external]
                               [--task <quest>/<tid>] [--card <KEY>]
guild pr untrack <owner/repo>#<n>
guild pr ready-check <owner/repo>#<n>
guild pr ack <owner/repo>#<n>
guild pr wait <owner/repo>#<n> [--timeout <dur>]
```

Example:

```
guild pr track acme/app#1044 --task wave1/T01 --what "add retry to the sync" --waits "checks"
```

- `track`: a party needs `--task`. An adventurer needs `--task` equal to its own. A health-job adventurer passes no `--task` (`--card` optional). A PR already merged at track time never counts as a merge (`pr track` never inspects `mergedAt`).
- `set` needs at least one option. Absent options leave a flag unchanged.
- Relink: `set --task` and `--card` change the task or card a PR is linked to. An adventurer's PR takes `--card` only. A party's task must be one of its own. Only the owning party or adventurer may relink or `untrack`; the web board offers Relink and Untrack as the human. Use them when a merged PR only refined a spec and its card should not be reported as not done.
- `untrack` drops the PR row and its drift findings (event `pr.untracked`). Own PR only.
- Lifecycle comes from GitHub. `guild sync --source gh` owns readiness: an open PR that is Ready for review becomes `ready`, an open draft keeps `converging` and otherwise (including a stale `ready`) becomes `draft`. Merged and closed PRs become `merged` and `closed`. Agents mark a PR ready with `gh pr ready <n>`. `pr set --lifecycle` stays for the `converging` nuance. `--lifecycle ready` on a PR still draft on GitHub prints a hint, and the next sync reverts it.
- Human flags, never touched by sync:
  - `--needs-ask-answer`: the PR is stopped until the human answers an ask. It blocks the PR in the merge queue. A PR also counts as needing an answer while an open ask refs it (`pr:<owner/repo>#<n>`), computed at read time, so answering or dismissing the ask unblocks it with no `pr set`. The queue, `pr ready-check`, the board and the web PR pill show `needs-ask-answer (ask #N)`. `--no-needs-ask-answer` clears only the manual flag. A PR with the old `needs-human` lifecycle becomes `draft` with `needs-ask-answer` set, live and in `guild rebuild`.
  - `--needs-human-pr-review`: the human should review before merge. It does not block.
- Urgency marks, never touched by sync: `--fixes-main` (the PR repairs a broken main) and `--fixes-flaky` (it fixes flaky tests). Both can be set at `track` and flipped on `set` with their `--no-...` forms. They do not block the PR: they move it to the front of the merge queue and of `guild next`. They are a claim about the PR, independent of `guild main red`: the mark is honoured whether or not any source says main is red, and merging the PR never clears the red mark.
- Manual block: `--blocked-external "<reason>"` (the flag keeps its name) marks a PR that waits on something outside development (a decision, a meeting). Sync never clears it, `--no-blocked-external` does. See [Merge queue](#guild-merge-queue) for its effects. The web shows a `blocked: manual` pill with the reason and Block manually (asks for a reason) and Unblock buttons on the PR card and its queue entry. They record the same `pr.set` event with no party.
- `ready-check` first refreshes that one PR from GitHub (same refresh as `guild sync --source gh`, merge side effects included). When `gh` fails it adds `- note: state as of last sync` and keeps the stored state. It then computes the queue over every open tracked PR (cross-party stacks, pins and task dependencies count) and prints `<ref> <human state>` (`ready`, `ready (CI pending)`, `waiting` or `blocked`), then one line per item:
  - `- <blocker>`, `- <missing>`, `- wait: <x>`, `- note: <x>`;
  - `- gate: ...`: draft (with the `gh pr ready <n>` hint), needs human review, `N review comments since last read`, main red.
- A PR is human-ready when it is not draft, has no unresolved thread, has no comment or review by another author after the head commit (unknown counts as none), has a valid review trace when the project configures a validator, and has green CI on the head. `- review trace invalid: <reason>` makes it `blocked`. `- review trace not validated: <reason>` makes it `waiting`.
- Without any check on the head, the state is `ready (CI pending)` when the project's CI label is absent from the PR or main is blocked by billing. Otherwise it is `waiting` with `- no checks on head`. A PR behind a PR that is not human-ready is `waiting` (`- waits on <ref>`).
- `ready-check` exits 0 only when the action is `merge`, the state is `ready` or `ready (CI pending)` and there is no gate. Otherwise it exits 1, and it always exits 1 for a manually blocked PR and while review comments are unread.
- `ack` marks the PR's review comments as read. Unread comments are the PR's comments and reviews that no `guild next` or `pr ack` has marked. Read them, then ack. The web queue detail shows the same gate and a `Mark N comments read` button (it never calls `gh`).
- `wait` blocks until something changes. See [Waiting for a change](#waiting-for-a-change).
- Behind base: for each open tracked PR with a `branch` and a located clone, the board counts `git rev-list --count origin/<branch>..origin/<base>` (`<base>` is the PR's base branch, else the clone's) and shows a dim `N behind <base>` line, and a pill on the web PR card (`behind` in the board model), only when N is above 0. It is read from local refs at read time and stored nowhere, so a branch pushed from another machine, or missing locally, shows nothing. It is informational: not a review reason, and it changes no order, wait or exit code.

### `guild finding`

Counts recurring audit and review finding classes.

```
guild finding list
guild finding record <owner/repo>#<n> --class <slug>
```

- `record` counts a class once per PR. With `finding_guard_threshold` set, one project notice asks for an architecture guard when the class repeats that many times.
- `list` prints the finding classes of the project with PR counts.

### `guild sync`

Refreshes stored state from GitHub, the SDD, the tracker or local clones.

```
guild sync --source gh|sdd|tracker|bases [--all-projects]
```

- `--all-projects` visits every project config with an `sdd` (or `tracker`) block and skips the rest without a failure. A project whose sync fails (unreadable SDD root, `acli` missing or not logged in) is reported as `<project>: <reason>`, the run exits non-zero and the previous tracker snapshot is kept.
- `guild` has no daemon, so a sync only happens when something runs it ([Background jobs](#background-jobs)). In a raid, keep a watcher running, for example `watch -n 300 guild sync --source gh`, or `/loop 5m guild sync --source gh` from a session that supports it.
- `--source bases` runs `git fetch origin <base>` in each located clone of every project, whatever `fast_forward_base` says. It makes no GitHub call and touches no tracker or SDD data. It only updates `origin/<base>`; local branches and worktrees are never touched. A failed fetch is a sync failure (`<repo>: base fetch failed: <error>`). `--source gh` does not fetch bases.

**Merge notices.** When `sync --source gh` sees a tracked PR flip to `merged` during that sync (a PR already merged at `pr track` time does not count), it posts one notice per raid the owning party is an active member of. The author is the owning party, so every other member gets it and the owner does not. The TTL is a fixed 12h. A party in no raid gets no notice. The text is:

```
<repo>#<n> merged in main (<quest>/<tid>: <what>). Parties with open branches: rebase.
```

- When the PR's linked card is not done, or its SDD task is not marked done, the notice ends with `Owner follow-up: move <KEY> to Done; mark <tid> done in <epic> tasks.md.` (only the parts that apply).
- A PR tracked with `--card` shows `<card>: <what>` in place of `<quest>/<tid>: <what>`. A seeded PR with neither shows just `<what>`.
- With `shared_areas` in the project config (globs relative to the repo root, matched with `fnmatch`) and the owning party in at least one raid, sync makes one extra `gh pr view --json files` call. Any matching glob is appended as `Shared areas touched: <glob1>, <glob2>`. If the call fails, the notice still posts without that line and the failure is a sync failure (non-zero exit).
- A merge is announced at most once, ever: the payload carries `announces: pr:<repo>#<n>`, and sync skips posting when a notice (active or not) with that value exists. That is safe across a re-sync or a `rebuild` followed by a `sync`.
- Migration version clash: when the project sets `migration_paths`, every `sync --source gh` lists the changed files of each open tracked PR of the project's repos (one `gh pr view --json files` call each), keeps those matching a glob and takes the leading digits of each filename as its version. When two or more distinct open PRs carry the same version, a notice naming the version and the PRs goes to every raid of each involved party. It is announced once per (project, version, PR) through `announces: migration:<project>:<version>:<repo>#<n>`. A failed files call is a sync failure. Parties in no raid get no notice.
- Shared-area claims are released by the same sync. When the project has `shared_areas` and the owning party is in a raid or holds an active `area:` claim, the changed files are fetched once (shared with the notice) and every `area:<glob>` claim of the owning party whose glob one of them matches is released with a normal `claim.released` event. Other parties' claims and `task:` claims are never touched. If the files call fails nothing is released and it is a sync failure. When something was released and the owner is in a raid, the notice ends with ` Released: <glob1>, <glob2>.`
- Base fast-forward: with `"fast_forward_base": true`, a sync that detects a merge updates the local base branch of each merged repo once per run. Local clones are the git main checkouts (not linked worktrees) matched by the project's `paths` globs whose `origin` URL (https, ssh or path form) ends in a `github.repos` entry. The base branch is read from `origin/HEAD`. Steps: `git fetch origin`; if the base is not checked out in any worktree, `git fetch origin <base>:<base>`; if it is checked out and that worktree is clean, `git merge --ff-only origin/<base>`. A dirty worktree or a diverged base is left untouched and a `project:<name>` notice `local <base> of <repo> N commits behind origin, not updated: <reason>` is posted, at most once per origin tip. Absent or `false` means guild never mutates a clone.
- Per-PR lifecycle commands also fire from this sync ([Lifecycle commands](#lifecycle-commands)).

### `guild base`

Pauses or resumes the bases fetch of a repo.

```
guild base pause <owner/repo>
guild base resume <owner/repo>
```

- A paused base is skipped by `guild sync --source bases` and by the fast-forward after a merge. Use it when you are not working on that repo.
- The repo must belong to a project. Pausing twice, or resuming a base that is not paused, fails. The pause is stored (`base_pauses`) and replays in `guild rebuild`.
- `guild board` and the web header read local base drift live with `git rev-list`: one line per clone, `<repo> <base>: N behind` (`, M ahead` when above 0) or `<repo> <base>: up to date`, then `(fetched Xm ago)` or `(never fetched)` from the mtime of `FETCH_HEAD`. Nothing is stored.
- A clone without `origin/HEAD` shows `<repo>: no origin/HEAD (git remote set-head origin --auto)`. A failed comparison shows `<repo> <base>: cannot compare`. Both are warnings. A paused base shows `<repo>: paused`, without a warning. A `paths` entry that is not itself a clone also yields its direct child directories that are clones.
- The web header "bases" section (model key `bases`, left of "resources") shows a warning pill when behind, an ok pill when up to date and a neutral `paused` pill. Each line has `pause` or `resume` buttons (`POST /api/bases/<owner>/<repo>/pause|resume`, same function as `guild base`).

### `guild main`

Marks a repo's main branch red or green by hand.

```
guild main red <owner/repo> --reason "<text>"
guild main green <owner/repo>
```

- A repo is red when any source says so. `red` sets the manual mark (event `main.marked`, source `manual`). `green` clears only the manual mark. The `gh` mark clears on the next sync that sees the base branch green.
- The `gh` source (event `main.status_synced`, one event per change, source `gh`): `guild sync --source gh` reads the check runs of the base branch (`gh api repos/<repo>/commits/<branch>/check-runs`) for each project repo with a local clone and a known base branch. It is red when any run failed, was cancelled, timed out or needs action. A failing check run named `Dependabot` (Dependabot's own update job, not CI) never counts.
- When no check run of the head commit fails, it also reads the last 30 workflow runs of the base branch (`gh run list --branch <branch>`). It is red when the latest decided run of a workflow failed, timed out or failed to start (reason `workflow <name> failed @ <sha7> (run <id>)`). This catches a repo whose CI on the base runs on a schedule or by hand. Runs in progress, cancelled or skipped fall back to that workflow's previous run, a later green run clears it, and Dependabot update runs (event `dynamic`) never count. The projection is `main_status`.
- Main blocked by billing: when GitHub Actions cannot run because billing failed, every job of main fails without starting. The sync fetches the annotations of each failing run (`gh api repos/<repo>/check-runs/<id>/annotations`, only for runs that have any). When every failing run carries `recent account payments have failed` (or has no annotations and finished within 5 seconds of starting), it stores the mark with `external` = `billing` (`main_status.external`, carried by the `main.status_synced` payload; events without it replay as an ordinary red). A single failing run with another cause keeps main red.
- Effects of billing: the queue shows `0. MAIN BLOCKED (billing) <repo> → re-run main once billing is fixed` instead of `MAIN RED`, as do `guild board` and the web card. `guild pr ready-check` lists the note `main blocked: billing` and does not fail on it. The push hook does not refuse and warns `main of <repo> is blocked by billing: CI will not run`. Re-run main's last run once billing is fixed; the next sync clears the mark.
- The same test runs per open PR with failing checks, over the check runs of its head commit (`prs.checks_billing`: 1 billing, 0 a real failure, empty when nothing fails; it never moves the PR's last activity). Such a PR gets the label `checks blocked by billing (n)`. It is no longer a `checks failing` fix reason in the queue, a `pr ready-check` blocker, a `checks-failing` party wait or a `failing checks` line of `guild next`. A draft with only such failures counts as a green draft and shows `ready (CI pending)` with the note. If the extra call fails, the PR counts as a real failure and the sync reports it.

### `guild merge-queue`

Prints every open tracked PR in the order to merge by hand, with the next action for each. **Guild never merges.** The output is advice for a human, who merges and re-runs the command after each merge.

```
guild merge-queue [--raid <name> | --party <name>]
guild merge-queue --head [--raid <name> | --party <name>]
guild merge-queue pin   <owner/repo>#<a> --before <owner/repo>#<b>
guild merge-queue unpin <owner/repo>#<a> --before <owner/repo>#<b>
```

Example:

```
merge queue · raid ci · synced 4 min ago
0. MAIN RED acme/app — checks failing: lint (gh) → fix before anything
1. acme/app#1044  alpha  T01  unblocks 2 — merge (ready, checks ✓17; before acme/app#1047 (task T02 depends on T01))
▶ next action: 2. acme/app#1049  beta  T03  unblocks 1 — fix: checks failing (2) → beta
3. acme/app#1047  beta  T02  unblocks 0 — fix: waits on acme/app#1049 → beta
4. acme/app#1052  gamma  T07  unblocks 0 — wait: checks pending (3)
5. acme/app#1055  gamma  T08 [draft]  unblocks 0 — promote: gh pr ready → gamma (ready, checks ✓9)
6. acme/app#1058  gamma  T09  unblocks 0 — merge (ready, checks ✓9)
guild never merges: merge in this order by hand; re-run after each merge
```

- It is read-only: no network call, no event. The queue is only as fresh as the last `guild sync --source gh`. The header says `synced N min ago`, the latest sync among the PRs shown.
- Scope: `--raid` takes the open tracked PRs of the raid's active members, `--party` those of one party. They are mutually exclusive. Without a flag, a bound session uses its raid when its party is in exactly one, errors listing them when it is in several, and uses its own party when it is in none. A human terminal or an unbound session must pass a flag.
- `--head` prints only the first entry whose action is `merge` or `review: human, then merge`, as `<ref> <party> <task>`, or `no PR ready to merge`. PRs blocked by something outside development are skipped.
- Blocked PRs stay in place: if the top PR is blocked, fixing it is the first thing to do. `▶ next action:` marks the first blocked PR above at least one PR whose action is `merge`.
- Branch: the full branch name ends each queue line.

**State.** Only merge blockers decide the state, in this precedence:

- `blocked`: a check is failing, `mergeable` is `CONFLICTING`, the review decision is `CHANGES_REQUESTED`, review threads are unresolved, the merge state is `BEHIND`, a task its own task depends on (SDD `Depends on`, through the quest's epic) is not done by the same resolver `guild next` uses, it needs an ask answer (manual flag or an open ask), or a PR that must come before it (by task dependency or pin, transitively) is blocked. Every reason that applies is listed: `needs ask answer`, `checks failing (N)`, `merge conflict`, `changes requested`, `N unresolved threads`, `behind base`, `waits on task Txx`, `waits on <ref>`. Missing review data counts as no signal.
- `waiting`: not blocked, but checks are still running (`checks pending (N)`), or a PR that must come before it is itself waiting, or ready but still draft (`waits on <ref>`).
- `ready`: neither of the above.

Check counts come from the `statusCheckRollup` of `gh pr view` (check runs and legacy commit statuses). A check run that has not completed and a status `PENDING` or `EXPECTED` count as pending. `FAILURE` and `ERROR` statuses count as failing. Skipped and neutral runs are not counted. The pending count is stored in `prs.checks_pending` (rebuilt from the `pr.synced` event; older events replay as unknown). Failing beats pending. Merged and closed PRs never appear.

**Labels and action.** Labels show in brackets after the task, in this order: the type (`[feat]`), `draft` and `converging` (lifecycle from GitHub), `fixes-main` and `fixes-flaky` (urgency marks), `needs-ask-answer` and `needs-human-pr-review` (human flags). Only `needs-ask-answer` blocks. A draft that is otherwise `ready` is worth promoting; one that is blocked or waiting is not.

| State | Label | Action |
|---|---|---|
| blocked | any | `fix: <reasons> → <party>` |
| waiting | any | `wait: <reasons>` |
| ready | `draft` / `converging` | `promote: gh pr ready → <party>` |
| ready | `needs-human-pr-review` | `review: human, then merge` |
| ready | none | `merge` |

Waiting and ready actions are followed by order notes in parentheses (`ready, checks ✓N`, `before ...`, `after ...`, `pinned ...`).

**Order.** All open PRs are put in a topological order over hard constraints. Ties between PRs free to go first are broken by value:

1. SDD task dependencies between the PRs' tasks.
2. Pins (`X before Y`). A pin that involves a merged or closed PR is ignored. A pin whose first PR is blocked keeps that PR in place and the second one waits on it.
3. Among free PRs, one marked `fixes-main` or `fixes-flaky` goes first (both weigh the same), with `fixes a broken main` in its order notes. A mark never jumps a task dependency or a pin.
4. Among the rest, the one that unblocks the most goes first (`unblocks N`: the distinct open PRs that depend on it, directly or transitively, plus the open PRs of the same repo that touch the same project `shared_areas` glob), then the lower PR number, then the repo.

- If pins and task dependencies contradict each other, the PRs involved are listed at the end as blocked with the cycle named (`fix: ordering cycle ...`).
- Stacked PRs: a PR whose base branch is the branch of another open PR of the same repo merges after it. The queue shows `after X (stacked on it)` and `before Y (it is stacked on this)`. A pin cannot invert the stack (rejected as a cycle).
- Main red: a red base branch comes first, as row `0.`, for every repo among the shown PRs (see [`guild main`](#guild-main)).
- Manual block: a PR with `--blocked-external` is `blocked` with reason `manual block: <reason>`, keeps its place and has the action `manual block: <reason>`. PRs queued after it (pins, task dependencies, stacks) are blocked too, with the action `waits on manually blocked <ref>: <reason>`. None of them is the head of the queue, the `next action` target or a `guild next` item. They are excluded from `max_open_prs_per_party`, `max_open_prs` and `max_open_prs_per_file`.
- Shared data: for every open PR whose party is an active raid member or holds an active `area:` claim, in a project that sets `shared_areas`, the sync makes one `gh pr view --json files,additions,deletions,createdAt` call and stores the matched globs (`pr_shared_areas`), the diff size and the creation time (`prs.additions`, `prs.deletions`, `prs.created_at`, rebuilt from `pr.synced`). PRs of parties outside raids with no claims cost no extra call, and their overlaps are unknown to the queue. A failed call is a sync failure (non-zero exit) and keeps the previous rows.

**Pins.** `pin <a> --before <b>` records that `a` merges before `b` (event `merge_queue.pinned`, with the author party or `human`; projection `merge_queue_pins`). `unpin` removes it (`merge_queue.unpinned`) and still works after a PR merges.

- Both PRs must be tracked and open to pin.
- Who may pin: when both PRs belong to members of the same raid, any active member of that raid or the human. Otherwise only the party that owns both PRs, or the human. The human is a session-less terminal. A bound session acts as its party. An unbound session is refused.
- A pin that would close a cycle with pins, stacks or task dependencies is rejected naming the cycle (`pin would create a cycle: a -> b -> a`). A duplicate pin and an `unpin` of a missing pin are errors.

### `guild review-md`

Prints the PRs ready for the person as one markdown document, in merge-queue order.

```
guild review-md [--raid <name> | --party <name>]
```

- Scope flags and rules are those of `guild merge-queue`.
- A PR is listed when it is `ready` (not draft), its human state is `ready` or `ready (CI pending)`, it is not blocked by something outside development, its action is `merge` or `review: human, then merge`, and its repo has no red main (a main blocked by billing does not exclude it).
- Each PR is `- [ ] <owner/repo>#<n> <title> — <url>` followed by indented lines: `review: human first` for the human-review action, `checks: <n> passing` (also failing and pending counts) and one `note: <x>` per note of `guild pr ready-check`.
- With nothing to list it prints `Nothing is ready for you.` It exits 0 either way. The output carries no tool-internal names, so it can be pasted outside the CLI.
- On the board: `guild board` prints a `READY FOR YOU` section right after `NEEDS YOU`, and `guild web` shows a "ready for you" section under the open asks (model key `ready_for_you`). Both use the same rule, in the board's queue order (raid queues first, then one per party outside raids), each PR once: `<ref> <title> · <party>`, `· review first` for the human-review action, and one indented `note:` line per note. With none it prints `READY FOR YOU · nothing` (web: `nothing is ready for you`).
- `guild board --party` and the web party view keep that party's PRs. `guild board --raid` and the web raid view keep every PR whose queue is in that raid, so a PR shows under each raid whose queue contains it. `guild review-md --party X` recomputes the queue over that party alone, while `guild board --party X` filters the board's list, so cross-party pins can make them differ.

### Lifecycle commands

A project can declare a command per PR lifecycle event in its `lifecycle` config block (see [Configuration](configuration.md)). Guild launches it without a model, from the main checkout, and records the outcome. It never learns what the command does.

```json
"lifecycle": {
  "on_pr_merged": {"command": ["scripts/cleanup-merged.sh", "--dry-run"], "timeout_minutes": 30},
  "on_pr_closed": {"command": ["scripts/cleanup-merged.sh"], "timeout_minutes": 30}
}
```

```
guild lifecycle run <on_pr_merged|on_pr_closed> [--repo <owner/repo>] [--dry-run]
```

- Exit codes: an entry may add `"ok_exit_codes": [5]`, a non-empty list of unique integers from 1 to 255. A command that exits with a listed code is recorded as `ok` and posts no notice. Any other non-zero exit stays `failed`.
- When it fires: `guild sync --source gh` sees a tracked PR become `merged` (`on_pr_merged`) or `closed` without merging (`on_pr_closed`). PRs already merged or closed when tracked, seeded PRs and anything before the PR was tracked never fire.
- Argv only: guild runs exactly the declared argv with no shell and no interpolation of PR data, and never appends flags. A dry-run flag in the config is the project's own choice.
- Where and how: from the main checkout of the first triggering repo (sorted), in its own process group, blocking, after the rest of the sync pass. When `timeout_minutes` elapses (capped at 1440) the whole process group is killed. A missing checkout is an error, never a fallback. The command runs with stdin closed. Output goes to a temporary file, so a descendant that detaches from the process group cannot hold a run or its lock open past the timeout.
- Debounce and lock: triggers seen in one pass are grouped per project and event and run once. A lock per project and event (`$XDG_STATE_HOME/guild/lifecycle/<project>-<event>.lock`) stops overlapping runs. A run that finds it held is recorded as `skipped` (reason `locked`) and its triggers are lost: guild does not retry them.
- Record: a local `lifecycle.ran` event with the project, event, repo, triggers (`acme/app#12`, or `manual`), argv, cwd, status (`ok`, `failed`, `timeout`, `error`, `skipped`), exit code, duration and the last 2000 characters of merged stdout and stderr with control sequences stripped. The tail stays local: never exported, never in a notice. It can contain secrets the command prints. Any error while handling a group is recorded with status `error` and does not stop other groups or the sync.
- Failure notice: a failed, timed-out or unlaunchable command, or a missing checkout, posts one notice to `project:<name>` (12h) such as `lifecycle on_pr_merged failed for acme (exit 1): see guild history`. It carries no output and no argv. Sync does not count it as a failure and its exit code is unchanged.
- By hand: `guild lifecycle run` resolves the project from the current directory and the checkout from `--repo` or the single clone (several clones need `--repo`). `--dry-run` only prints `would run: <argv> (cwd <path>, timeout 30m)` and records nothing. A real run takes the same lock, records the trigger `manual`, prints `lifecycle on_pr_merged: ok (exit 0, 3.2s)` and exits 1 on failure, timeout or error.
- Trust boundary: the command runs unattended with your privileges, right after the main checkout is fast-forwarded. A merged PR that edits a repo-relative script makes the next run execute that new code. Point `command` at an absolute path outside the repo, or at a script you review.
- Out of scope: `on_main_red` (sync cannot tell a first red observation from a new failure), `on_worktree_created`, a resource officer (see the `officers` epic), detached runs, retries, re-running lock-skipped triggers, and moving the runner under a scheduler.

### Waiting for a change

`guild ask wait <id>` and `guild pr wait <owner/repo>#<n>` block until something changes, so a session can run them in the background and wake up on the change.

```
guild ask wait <id> [--timeout <dur>]
guild pr wait <owner/repo>#<n> [--timeout <dur>]
```

- They poll every 15 seconds and read only guild's stored state: no sync, no GitHub call, no write. A PR only changes in that state when a sync runs, so `pr wait` starts the due background syncs itself ([Background jobs](#background-jobs)).
- `--timeout` defaults to `2h` and ends the wait with exit 3.
- `ask wait` exits 0 when the ask is answered or dismissed and 1 on an unknown id. It never prints the answer: read it with `guild asks <id>`.
- `pr wait` exits 0 when the PR is merged or closed (also when it already is), when a comment or review by someone other than the PR author appears (the count is compared with the one at the start of the wait), or when its checks go from pending to finished. It exits 4 when no sync ran for 30 minutes. It prints one fixed line with the ref and counts, never comment text.
- Comments from the PR author's own account do not wake it. Notice-only comments configured with `human_ready.notice_comments` do not either.
- Exit 1 is an untracked or malformed ref, or a PR not synced since the comment count existed (run `guild sync --source gh` first). The count only moves with a sync: a comment deleted and another added between two syncs leaves it unchanged and does not wake.

## Asks, notices and claims

### `guild ask`

Asks the human a decision. Answering is only for the human.

```
guild ask "<question, at most 300 chars>" --context "<at most 2000 chars>" [--ref <ref> ...] [--option "..."] [--recommend "<option and why, at most 300 chars>"]
guild ask wait <id> [--timeout <dur>]
guild answer <id> "<text>"
guild dismiss <id>
guild asks [<id> | --all [--party <name>] [--since <dur>] | --answered [--page <n>] [--party <name>] [--since <dur>]]
```

Example:

```
guild ask "Ship the retry as a flag or always on?" --context "The sync retry changes timing for every project." --ref task:wave1/T01 --option "flag: opt in per project" --option "always on" --recommend "flag: no surprise for existing projects"
```

- `--context` is required. A question or context that carries many ids or paths prints a warning and the ask is still created.
- Refs: `pr:<owner/repo>#<n>`, `task:<quest>/<tid>`, `card:<KEY>`. A `card:<KEY>` ref is accepted when the key is in the synced `cards` of the asking party's project or fully matches that project's `sdd.key_ref`.
- With no `task:` or `card:` ref and exactly one task in progress, `task:<quest>/<tid>` is added and `auto-ref: task:<quest>/<tid>` is printed. With no ref and no single in-progress task, the ask is refused.
- When an ask is created, guild stores a snapshot of its origin: session id and name, the party's in-progress tasks, their epics, the card keys of the party's PRs and of those tasks, and the latest handoff file.
- `--recommend` states the option the agent recommends and why. `--context`, `--recommend` and the answer render paragraphs (blank line), line breaks and `**bold**` in the CLI and the web, and nothing else.
- `answer` and `dismiss` refuse inside a Claude Code session: run them from the human terminal or the web board. A raid member's ask goes to the human queue only. No other member gets it, and any bound session can answer through the normal inbox path.
- `ask wait` blocks until the ask is answered or dismissed ([Waiting for a change](#waiting-for-a-change)). It exits 0 on either, 1 on an unknown id and 3 on timeout (default 2h).
- `asks` lists open asks. `asks <id>` expands one in two tiers. First what decides it: question, context, options, recommendation, the task with its state, the card with its status and tracker link (`tracker.browse_url`), and the PR with URL, lifecycle and checks. Then `dig in`: the task SDD spec and tasks paths (the filesystem path with `root`, or `git:<ref>:<path>` with `git_repo` and `git_ref`), the origin snapshot and the command that resumes the asking session. On the web `dig in` is closed by default. Asks created before snapshots print `origin: not recorded`. Times are local (`YYYY-MM-DD HH:MM`). The same detail is served at `GET /api/asks/<id>` and opens from the `detail` control of each ask on the web.
- `asks --all` lists open, answered and dismissed asks in id order, with the answer and answer time of answered ones. `--party` and `--since` (on `created_at`) narrow it and need `--all` or `--answered`. `<id>` takes no filters.
- `asks --answered` lists only answered asks, newest answer first, 10 per page (`--page <n>`), each with party, answer and answer time. The web shows the same list in a collapsed "answered asks" section, served at `GET /api/asks/answered?page=<n>`.

**Ask ordering.** `guild asks` and the board summary sort open asks by how many of their refs are still blocked right now, computed at render time: blocked count descending, then `created_at` ascending, then id ascending.

- A `pr:` ref is blocked while the tracked PR's lifecycle is not `merged` or `closed`. An untracked PR ref counts as blocked (never assume done).
- A `task:` ref is blocked while the task's state is not `done`. An unknown task ref counts as blocked. A `card:` ref never counts as blocked.
- The board summary line adds `· blocks <n>` when `n > 0`. `guild asks` prints `blocks: <n> of <total> refs still open`, or `blocks: 0 of <total> refs still open (may be stale)` when every ref has resolved, a hint the ask can probably be dismissed.

### `guild notice`

Broadcasts a short message to a project, a raid or everyone.

```
guild notice create "<text>" --to project:<name>|guild|raid:<name> --ttl <dur> [--until pr:<owner/repo>#<n>:merged|closed]
guild notice close <id>
guild notice seen <id>|--all
guild notice unseen <id>
guild notices
```

- `create` always needs an explicit action ([decision](../sdd/decisions/20261111_notice-requires-an-explicit-action.md)). Notice text can then be any string, including `close`.
- A raid notice is valid only while the raid has at least one active member (a clear error otherwise). Any bound party, or the human, may post to it. It reaches a session's inbox (`prompt-submit`, `post-tool-use`, `brief`) only when that session's bound party is an active member at delivery time. Unbound sessions and the human terminal never get raid notices, and the sender's party never gets its own notice back, as with every scope. `guild notice targeting` is the single place that resolves whether a `project:`, `guild` or `raid:` scope matches the caller. `guild board` shows the raw `raid:<name>` scope on a raid notice.
- Every "unknown project" error lists the known projects, for example `unknown project 'x': known projects are acme, zeta` (or `known projects are none`).
- `seen <id>` marks an active notice as seen so new ones stand out. `unseen <id>` undoes it. `seen --all` marks every active notice (`N notices marked seen`). The id and `--all` are mutually exclusive and one is required. A seen notice is only a mark for the human view: it stays listed while active, and delivery (inbox cursors, `prompt-submit`, `post-tool-use`), the `session-start` brief and `guild brief` are untouched. The commands work for the human actor and for bound sessions. They fail for an unknown id, a notice already seen (or, for `unseen`, not seen) and a notice that is not active (closed or expired). The mark is per guild, not per reader. Storage: events `notice.seen` and `notice.unseen`, column `notices.seen_at` (`TEXT`, `NULL` when not seen); `guild rebuild` replays it.
- Author labels: `human` (no session), the party, `unbound session`, or `guild` for notices guild writes itself (sync, lifecycle, findings, raid pause). A label shows where a notice most likely came from; it is not authentication, since any process without a Claude session reads as `human`. Old notices read as `human`.
- `notices` lists every active notice, newest first, with issue time (local, `YYYY-MM-DD HH:MM`) and time left, unseen ones prefixed with `new` (`new #13 [party] text (scope, 2026-10-04 14:30, 5h left)`), and ends with `N new` when N > 0. `guild board`, `guild brief`, `guild web` and the inbox lines (`- notice #13 from party at 2026-10-04 14:30: "text"`) show the same time and order. The NOTICES section of `guild board` marks unseen ones with `new` (coloured on a terminal only) and its header reads `NOTICES · N active (M new)`.

### `guild claim`

Claims an area so parties do not edit the same thing.

```
guild claim <area> --ttl <dur>
guild claim check <area>
guild release <area>
guild claims
```

- `<area>` is an area, or `task:<epic>/<tid>` or `task:<quest>/<tid>`.
- `check` is read-only and fires no event. Exit 0 and `free` when no one holds the area. Exit 0 and `held by you until HH:MM` when your bound party holds it. Exit 1 and `held by party <p> until HH:MM` (to stdout, so a script can parse it) when another party holds it. From an unbound session or the human terminal, "held by you" never applies: any active holder gives exit 1. It accepts any area string, including `task:<epic>/<tid>` and a shared-area glob.
- `check` is a reserved word: an area literally named `check` cannot be claimed or read ([decision](../sdd/decisions/20261111_claim-check-is-a-reserved-word.md)). `guild claim check --ttl ...` is rejected clearly.
- Claims are released by `party close` and by a merge sync ([`guild sync`](#guild-sync)).

## Raids

A raid is a named channel parties join so a shared concern (CI, a shared file) has a deterministic audience. It exists while it has at least one active member. There is no create command.

### `guild raid`

```
guild raid join <name> --ttl <dur>
guild raid join <name> --until-leave
guild raid leave <name>
guild raid pause <name>
guild raid resume <name>
guild raids
```

- `join` takes exactly one of `--ttl <dur>` or `--until-leave`. The caller's bound party becomes an active member. A TTL join lasts until it expires, and joining again refreshes it. `--until-leave` has no expiry and ends only with `leave` or the `party close` cascade. Joining again switches mode: a TTL join over an until-leave membership sets a TTL, the other way clears it.
- `leave` removes your bound party. Leaving when not an active member is a clear error.
- `raids` lists every raid with its active members and each member's time left, or `until leave`. A paused raid shows `<name> (paused):`.
- `party close` cascades into every raid the party belongs to, as with claims.
- A TTL membership due to expire within 12h (`MEMBERSHIP_WARNING_WINDOW`) is warned once per (session, raid, expiry) in `prompt-submit`, `post-tool-use` and the session-start brief: `guild: raid <name> membership expires in <Nh> — renew with guild raid join <name> --ttl <dur> or --until-leave`. Renewing changes the expiry, so a later warning can fire again.
- `guild board --raid <name>` and the web raid view (`#raid/<name>`) narrow parties, asks and notices the same way. The web board model has a top-level `raids: [{name, members, paused}]` list.

### Pausing a raid

`guild raid pause <name>` marks the raid paused (events `raid.paused` and `raid.resumed`, table `raid_pauses`, rebuilt like everything else). Any active member, or the human, may pause or resume. Pausing a paused raid, or resuming one that is not paused, is a clear error.

While paused:

- `prompt-submit` and `post-tool-use` inject `raid <name> paused: finish current step and leave guild handoff` for every bound session whose party is an active member, once per (session, raid, pause) through a marker file shared by both hooks. A later pause injects again.
- `guild next` (single and `--all`) returns `nothing actionable` plus `raid paused: <name>` for those parties and does not advance their PRs or tasks.
- `guild board` shows `PAUSED` in the party's `raids:` line and a `raid <name> PAUSED` header with `--raid`. The web board model carries `paused` on each raid and membership.

`guild raid resume <name>` deletes the pause state and posts the notice `raid <name> resumed` to `raid:<name>` (8h TTL), which reaches members through normal notice injection.

The web `raids` section lists each active raid with a `Pause raid` button (inline confirm: pausing tells members to hand off), or a `paused` pill and a `Resume raid` button. `POST /api/raids/<name>/pause` and `/resume` (body `{}`) run the same commands. The human is always allowed (no session), as with `guild merge-queue pin`, and a human pause is recorded with `paused_by` `human`.

## Ideas

A backlog for loose ideas. An idea has a title, a description, a creation date and, optionally, a requester (free text), a deadline (`YYYY-MM-DD`) and a registered project. Ideas are local and never broadcast. The human and any session can add, edit and delete them.

```
guild idea add "<title>" --description "<text>" [--requester <text>] [--deadline YYYY-MM-DD] [--project <name>]
guild idea edit <id> [--title ..] [--description ..] [--requester ..|--no-requester] [--deadline ..|--no-deadline] [--project ..|--no-project]
guild idea delete <id>
guild idea link <id> [--party <name> | --adventurer <id>]
guild idea unlink <id> [--party <name> | --adventurer <id>]
guild ideas [<id> | --project <name>] [--exported]
```

- `ideas` lists by deadline ascending (no deadline last, ties by creation) and marks `overdue` the ones whose deadline is before today. `<id>` shows one in full. Each idea shows its creation date and, after an edit, its update date. An idea with no linked party shows `not linked yet`. `--exported` lists the exported ones.
- When a party or an adventurer starts work from an idea it runs `idea link <id>` (an adventurer session is detected on its own). A session links only itself. From the human terminal, one of `--party <name>` or `--adventurer <id>` is required. The party must exist and not be closed, the adventurer must be active, and linking twice is refused.
- `unlink` drops the link. It is refused once the party or adventurer tracks a PR.
- `ideas` and `ideas <id>` show `worked by: <party>, adventurer <id>, ...` (closed parties marked `(closed)`, adventurers that are not active marked with their state). Each party and adventurer block in `guild board` lists its `ideas`. The `adventurer done` final report lists the linked ideas. Promoting an adventurer moves its links to the new party. A done or dismissed adventurer keeps its links.
- When the work is done, the session runs `idea delete <id>`, which also removes the links. A deleted idea stays in the event log and `guild rebuild` deletes it again.
- Idea ids are local: do not copy them into PRs, commits or cards.

**Web.** The `ideas` section shows the same list in the same order with an `overdue` flag, a form to add one and `Edit` and `Delete` on each card. The description is a multi-line box and its line breaks are kept. The project select lists every registered project. The deadline is typed as `YYYY-MM-DD`. Each idea shows its linked parties with `Unlink`, and a select of active parties with `Link` (it links and unlinks adventurers too). The party card lists its ideas. The routes run the same functions as the CLI. Invalid input answers `422` with the message, a wrong type `400`.

- `POST /api/ideas/create`: body `{"title", "description"}` plus optional `requester`, `deadline`, `project`, each a string or `null`.
- `POST /api/ideas/<id>/edit`: body with the fields to change. `null` clears requester, deadline or project.
- `POST /api/ideas/<id>/delete`: body `{}`.
- `POST /api/ideas/<id>/link` and `/unlink`: body `{"party"}`.

### Moving ideas to another guild

These four commands are for the human terminal only. Agents never run them.

```
guild idea export (<id>... | --project <name>) --to <destination> --out <file.md>
guild idea unexport <id>
guild idea import <file.md> --receipt <receipt.md> [--project <name>]
guild idea confirm-export <receipt.md>
```

- `export` writes ideas to a new `.md` file (a heading plus one fenced JSON block) and hides them as exported. It never deletes them. The requester and the links are not written, because the requester may name a real person. Each idea gets a uuid that stays the same on a later export. The file is at most 256 KiB, so `guild realm send` can carry it. A plain copy works too.
- With ids, `export` refuses an idea already exported or linked to an open party or an active adventurer. With `--project` it takes every idea of that project and lists the linked ones it skipped.
- `import` reads the file in one transaction (all or nothing), gives each idea a new local id, skips the uuids it already holds, flags text that looks like an instruction and writes a receipt with the uuids this guild now holds.
- Carry the receipt back and run `confirm-export`. It deletes the exported ideas the receipt lists and reports the uuids it ignored. Check the sender that `guild realm fetch` prints first: there is no undo after the confirmation.
- `unexport` brings an idea back. It warns that both guilds hold it if the other side already imported it.
- Exported ideas leave `guild ideas` and the board count, and `idea link` refuses them.
- The web `ideas` section has an `Export` button on each idea and an export project action, both next to a destination field. The file is saved in `idea-exports/` under the guild data directory and its path is shown. A paste form imports an export file (the receipt is saved there too), another confirms a pasted receipt after a prompt, and a collapsed `exported` list offers `Unexport` and `Delete`. The routes are `/api/ideas/export`, `/api/ideas/export-project`, `/api/ideas/import`, `/api/ideas/confirm-export` and `/api/ideas/<id>/unexport`.

## Background jobs

Guild has no daemon and installs no systemd timers. Seven jobs keep the stored state fresh. Each starts, detached, when it is due and one of these runs: a session hook (`session-start`, `prompt-submit`, `stop`), a `pr wait` that sees no sync for 30 minutes, or `guild web`, which checks every minute while it runs, with or without a browser open. Leave `guild web` running (tmux, a login autostart) for a schedule like timers. An idle machine, with no session and no `guild web`, runs nothing.

| job | command | every |
|---|---|---|
| `sync-gh` | `guild sync --source gh` | 10m |
| `sync-sdd` | `guild sync --source sdd --all-projects` | 10m |
| `sync-tracker` | `guild sync --source tracker --all-projects` | 10m |
| `sync-bases` | `guild sync --source bases` | 1m |
| `resources-collect` | `guild resources collect` | 2h |
| `solo-tick` | `guild solo tick` | 10m |
| `compact` | `guild compact` | 1d |

- `resources-collect`, `solo-tick` and `compact` run at `Nice=19`.
- The last start of each job is a stamp file in `$XDG_STATE_HOME/guild/due/`. A job is due when its stamp is missing or older than its interval. The stamp is touched before the start, so two hooks never start the same job twice.

### Health jobs

`health_jobs` in the project config (see [Configuration](configuration.md)) names recurring jobs. A job is `due` when no adventurer on it has reported (`done`, dismissed or not) or the latest report is older than `every`. It is `running` while an adventurer on it is active, and `ok` otherwise. This is computed on read from the adventurers table: nothing runs on a timer and nothing launches by itself.

- `guild board` lists due and running jobs per project in a `HEALTH JOBS` section (hidden under `--party` and `--raid`). The web shows the same in `health jobs`. A due job carries the command `guild adventurer launch <name>` as text to copy. The web has no launch button.
- `guild adventurer launch <name>` is for the human terminal only. Run from a checkout of the project, it opens a tmux window named `health-<name>` in the first entry of the project's `paths` (the part before the first glob character) and runs `claude` there with the job's `command` as the first prompt, quoted for the shell as `guild revive` quotes its commands, and with `GUILD_ADVENTURER_JOB=<name>` in that process's environment. It refuses when tmux is missing or the window already exists. Guild records the window id it created (`health_window.launched`, table `health_windows`).
- After `guild adventurer done`, the `Stop` hook of that session closes its pane when the pane's window is a recorded one and is in the `guild` tmux session. A hand-started `claude`, a session in another window or any failed check is left open. This runs inside the session, so the web has no action for it.
- The `SessionStart` hook reads `GUILD_ADVENTURER_JOB`: in a new (`startup`) session that is not a party leader or an adventurer yet, it starts the adventurer for that job, as `guild adventurer start --job <name>` does. When it cannot, the hook output says why (`GUILD_ADVENTURER_JOB=<name> not applied: ...`).

### Solo players

`solo_players` in the project config (see [Configuration](configuration.md)) declares per-repo players. A solo player is a health adventurer with a configured prompt. Its identity is `(repo, job)`. A job is built in, with its own prompt, class and trigger, or defined in the config ([custom players](#custom-solo-players)). Built-in jobs:

| job | class | what its session does |
|---|---|---|
| `red-main` | cleric | fixes a red main with TDD, opens a PR tracked with `--fixes-main`, never merges |
| `dependabot` | artificer | makes open Dependabot PRs mergeable (stale, identity, scope and supply-chain gates, direct fixes on the PR branch; closes a stale single-dependency PR with `@dependabot close` and drops stale dependencies from a multi-dependency PR) and fixes a failing Dependabot update run through a normal PR; never merges |

```
guild solo list [--project <name>]
guild solo status [<owner/repo> <job> | --project <name>]
guild solo launch <owner/repo> <job> | --all | --project <name>
guild solo stop <owner/repo> <job> | --all | --project <name>
guild solo resume <owner/repo> <job> | --all | --project <name>
guild solo tick
guild solo say "<text>"
guild solo channel [--limit N] [--project <name>]
guild solo runs <owner/repo> <job>
```

- Each prompt has two parts. The rules always apply: the goal, never merge, how to track the PR, `guild solo say` and `guild adventurer done`. The steps are built in, unless the local clone of the player's repo has a skill named after the job, `.claude/skills/<job>/SKILL.md`. Then the session starts with `/<job> <owner/repo>` and follows that skill for the steps. The rules still win on merging, tracking and messages. The skill wins on the repo's own steps, such as how a PR becomes ready.
- `launch` and the tick open the window in that clone. Without a local clone, they open it in the project's first path with the built-in steps.
- `name` is only a board label. `class` on a built-in entry replaces its class. Each solo player is also a health job named `<job>-<owner>-<repo>` (the repo with `/` turned into `-`, for example `red-main-acme-app`), with `every` `1h` and the built-in prompt. `guild adventurer start --job <that name>` and the `GUILD_ADVENTURER_JOB` binding of the `SessionStart` hook accept it. The `HEALTH JOBS` section lists only jobs written in `health_jobs`.
- Solo players are active as soon as they are configured. The `solo-tick` background job runs `guild solo tick`, driven by sessions and `guild web`.

**Triggers.** They come from facts the sync stores:

- `red-main`: a `main_status` row of the repo is red and not blocked by billing, whichever source set it (`guild sync --source gh` or `guild main red`).
- `dependabot`: `guild sync --source gh` found an open Dependabot PR that is not mergeable (failing checks, conflicts, behind or dirty), or a failing latest Dependabot update run (runs with event `dynamic`, the latest completed run per ecosystem). It records `dependabot.synced` only when the counts change.
- The same sync announces each open Dependabot PR that is ready (mergeable, merge state clean, at least one check and all of them SUCCESS, NEUTRAL or SKIPPED) once in the solo channel, posted as the `dependabot` player (`<repo>#<n> ready to merge: <title>`). No session is launched. It records `dependabot.announced`, so a PR that breaks and turns green again is not announced twice.

**States.** A player is:

- `running`: an adventurer on its health job is active and its session is alive.
- `stalled`: that adventurer is active but its session is gone (crash, closed window, usage limit). The row reads `stalled: session gone, run guild adventurer dismiss <id>`. The tick does not launch it. Dismissing that adventurer makes the player launchable again.
- `due`: its trigger is on, nothing runs, and the last report (`done`, dismissed or not) and last launch are older than the 1h cooldown.
- `cooling`: the trigger is on but the last report or launch is newer. A backing-off row reads `cooling: same trigger`.
- `fixing` (`red-main` only): an open PR of the repo is tracked with `--fixes-main`. It holds the player and shows `fixing: waits on <ref>` until that PR merges or closes.
- `paused`: stopped by the human. Never `due`.
- `idle`: no trigger.

The cooldown is 1h. When the trigger text equals the one of the last launch (for example a Dependabot PR that needs a human), it is the player's retry wait instead, so a player that cannot fix its trigger does not relaunch every hour. The retry wait is `retry_after` of its config entry, by default 4h on `main-red` and 24h on `dependabot`. A different trigger keeps the 1h cooldown. A launch with no trigger (manual, main already green) or recorded before the trigger was stored counts as a different trigger. A launch younger than the cooldown keeps the player `cooling`, so a trigger that stays on while the new session binds, or after the human closed its window, does not launch it again.

Each row also shows its retry wait and an estimated next run: the time the cooldown ends on a `cooling` row, the next interval on an idle `every` player, `next tick` on a `due` row (the tick runs every 10 minutes while `guild web` or a waiting session is up) and `none` otherwise.

**Commands.**

- `list` (alias `status`) and the `SOLO PLAYERS` section of `guild board` (hidden under `--party` and `--raid`) and the web `solo players` show name or job, class, repo, trigger, state, retry wait, next run, last report time and last pending text. A due or idle row carries `guild solo launch <owner/repo> <job>` as text to copy. The web has no launch button. `list` and `channel` group by project and take `--project <name>`.
- `status` takes the scopes of launch: no argument for every player, `--project <name>` or `<owner/repo> <job>`. The last form adds the player's last 5 runs and last 10 channel messages. An unknown project or player is an error.
- `launch` is for the human terminal only. It opens a tmux window named `solo-<job>-<owner>-<repo>` the way `guild adventurer launch` does, even when the player is not due. `<owner/repo> <job>` is matched across all projects, so it works from any directory, as in `status`, `stop` and `resume`. It closes a finished window left open before launching, and refuses a running player or a stalled one (dismiss it first). A player closes its own window after `guild adventurer done`, so its prompt ends with one short `guild solo say` instead of the long final report.
- `launch --all` launches every configured player and `launch --project <name>` those of one project, whatever their trigger, skipping the running and stalled ones. They print one line per player (`<name> launched`, `<name> skipped: running`, `<name> skipped: stalled, run guild adventurer dismiss <id>`, `<name> not launched: <error>`) and go on after a failure. The pair, `--all` and `--project` exclude each other.
- `stop` and `resume` take the same three scopes, but all players need `--all`: with no argument they are an error, so a mass stop is never an accident. Both are for the human terminal only.
  - `stop` on a `running` or `stalled` player closes its `solo-<job>-<owner>-<repo>` window (a missing window is fine), dismisses its active adventurer, pauses the player and posts `<name> stopped by the human` to the channel. On any other player it only pauses it and posts `<name> paused`.
  - `resume` lifts the pause and posts `<name> resumed`.
  - A pause is a `solo.paused` event and `solo.resumed` ends it, so it survives `guild rebuild`. A `paused` player is never `due`: the tick leaves it alone, and `launch` skips it with `<name> skipped: paused, run guild solo resume <owner/repo> <job>`. The board and the web show `paused` with the resume command as text to copy.
  - Output is one line per player (`<name> stopped`, `<name> paused`, `<name> already paused`, `<name> resumed`, `<name> not paused`, `<name> not stopped: <error>`), continuing after a failure.
- `tick` launches every `due` player the same way. It is the `solo-tick` background job. It is for the human terminal and the background job and refuses inside a Claude Code session. It closes the window a `due` player still has before launching it again, prints one line per player it could not launch (for example `tmux not found`) and still exits 0. Each launch, manual or not, records a `solo.launched` event with the trigger text and posts `<name> (<class>) started on <repo>: <trigger>` (`manual launch` when no trigger is on) to the solo channel, not to a project notice, so launches do not interrupt other sessions. See [the decision](../sdd/decisions/20261101_solo-players-launch-on-trigger.md).
- `say` posts to the channel. It runs only inside a session bound as the adventurer of a solo player, strips control sequences and refuses empty text or text over 300 characters.
- `channel` prints the latest messages newest first (default 20). The channel holds only important messages: the launch line, `<name> finished: <pending>` when its adventurer ends, and what the player posts with `say`. The web shows the latest 20 as a read-only feed at the top of the solo players section (board JSON key `solo_channel`). Every item carries its `project`.
- `runs` prints the last runs of a player, read from its adventurers: start time, `running`, `stalled` or `done`, duration and pending report, then the PRs the run tracked with their lifecycle. The web lists the last 5 per player under a collapsible `runs`. The board JSON carries them as `runs` on each player.

**Where the work shows.** The channel is a log. The lists that clear by themselves show it too:

- Each ready Dependabot PR is a row of READY FOR YOU (`<repo>#<n> <title> · from <name>`, after the tracked PRs, unfiltered board only) until it merges or stops being ready.
- A solo player whose last run ended with pending work other than `none` is a row of NEEDS YOU (`⚑ <name> [<class>] <repo>: <pending>`) while its trigger is still active. The web needs-you view shows the same rows and counts the ready ones in the `ready` badge.
- The solo players view, the board and `guild solo status` list the PRs to merge under the `dependabot` player (`to merge: <repo>#<n> <title>`). A ready PR whose merge state GitHub has not computed yet (`UNKNOWN`, right after the base branch moves) keeps its place until GitHub reports a definite state.

#### Custom solo players

An entry with a `job` that is not built in defines its own player. Every key is required, nothing is defaulted, and `repo` is the home repo: the repo whose clone is the working directory of the session. Put the repo a command targets inside the command.

```json
{"repo": "acme/app", "job": "sec-audit", "name": "warden", "class": "red",
 "command": "/security-audit acme/api quick", "trigger": "every 7d"}
```

- `job`: a slug like other names, not `red-main` or `dependabot`.
- `command`: the prompt the session starts with, a non-empty string that does not start with `-`. Guild appends the rules every built-in prompt carries: never merge, track PRs with `guild pr track` without `--task` (plus `--fixes-main` when the trigger is `main-red`), `guild solo say` only for important things, one short message before `guild adventurer done`.
- `class` and `name`: free labels shown on the board.
- `trigger`: when the player is due. `main-red` and `dependabot` behave like the built-in jobs of that name (including the `fixing` hold and the `to merge` list). `every <duration>` (for example `every 7d`, at least `1h`) is due when it has no report and no launch yet, or the last report or launch is older than the interval, and never backs off.
- `retry_after`: optional, how long a `main-red` or `dependabot` player waits before retrying the same trigger (for example `2h`, at least `1h`). Refused on an `every` trigger.
- Built-in entries accept `repo`, `job`, `name`, `class` and `retry_after`. `command` and `trigger` are refused there. The board and `guild solo list` show each player's schedule (`on main-red`, `on every 7d`).

## Web board

### `guild web`

Serves the same board in a browser, with more room for filtering, collapsing and linking out.

```
guild web [--port <n>]
```

```
guild web: http://127.0.0.1:<port>/#t=<token>
```

- `--port` defaults to 8765. `--port 0` lets the OS pick a free port. It always prints the real resolved URL before serving, with the session token in the fragment (never sent to the server). Open that exact URL.
- The server serves the page files it loaded at start, so restart `guild web` after updating guild.
- Every feature works in both the CLI and the web. A web write runs the same `guild/commands` function as the CLI, as the human actor.
- While it runs, it is also the ticker of the [background jobs](#background-jobs).

**Layout.** The page is a sidebar next to a pane, using the full width. Under 480px the sidebar sits above the pane. The sidebar links to views kept in the URL hash, so a reload or the 10-second refresh keeps them:

| Hash | View |
|---|---|
| `#needs-you` (default) | open asks, ready for you, answered asks |
| `#party/<name>` | one party |
| `#raid/<name>` | asks, merge queue, tasks per day, parties, memory |
| `#adventurers` | adventurers and health jobs |
| `#solo-players` | solo players, one tab per project, each with its players and then its channel. `#solo-players/<project>` opens that tab, `#solo-players` the first |
| `#ideas` | ideas |
| `#quests` | quest board |
| `#overview` | notices, raids, drift, projects |

- The menu lists needs you, adventurers, solo players, ideas, quest board and overview first, with counts for asks, ready PRs, blocked and context-high parties (a count above zero is a pill coloured by type), active adventurers, solo players, ideas, open quests and new notices. The solo players item is collapsed by default and opens to one link per project (it opens by itself on a project tab).
- After them come the parties grouped by raid (a party in two raids shows under both) and a `parties` group for parties outside raids. Each party row shows its state badge, open asks, the work left and `stopped without report`. Parties sort by attention: waiting on permission, waiting on an ask, context high, waiting on input, waiting on a limit, stopped with work, working, queued, parked, blocked. A raid header shows its worst member state.
- A party view shows the whole merge queue of its raids, or its own queue when it has no raid. The header keeps the PR state filter.

**Progress.** Under the merge queue, the party and raid views show the tasks done out of the total of the active quests with a bar, one bar per quest, the active, blocked and queued counts, and the blocked tasks grouped by reason (the tooltip lists their ids). A raid view sums its member parties. `guild board --party` and `--raid` print the same as `PROGRESS · <done>/<total> tasks done (<pct>%)`.

**Tasks per day.** Also under the merge queue: a table of the last 15 days, today included, one column per local day. `created` counts tasks added to the party's quests that day, `done` the tasks finished that day. A task counts for the party that owns its quest now.

- `-` marks a day with no session of the party and no task created or done. `0` means a session ran but created or finished nothing (model key `active`). A session idle across midnight leaves no event on the second day, so that day also shows `-` (the web cell's tooltip and a line under the CLI rows say so).
- `x` marks a day before the party's first leader started (model key `existed`).
- A raid view sums its member parties, and a day is active (or existed) when any member was. `guild board` prints the same rows as `TASKS PER DAY · last 15 days`.

**Party waits.** Each party card shows a `waits on:` row with one pill per wait (model key `waits`), with a tooltip that explains the kind.

**What it shows.**

- Open asks: question, party, options, refs, how many refs still block it, a collapsible context, a `detail` control that loads `GET /api/asks/<id>`, and a collapsed "answered asks" section.
- Active notices, and a "ready for you" list ([`guild review-md`](#guild-review-md)).
- The merge queue: one card per raid, plus one per party outside raids that has open PRs. It has a `MAIN RED` row per red main, then numbered PR links with label pills (`draft`, `converging`), the human-ready pill (`ready` or `ready (CI pending)`), checks, party, task, state, `unblocks N`, the action and the `next action` marker, the reasons as pills, a collapsible ready-check detail per PR (the same content as `guild pr ready-check`) and a `next to merge: <ref> (<party>)` line, or `no PR ready to merge`, matching `guild merge-queue --head`. It is read-only, in the order of `guild merge-queue`, with `synced N min ago`. The party view shows the whole queue of its raids (or its own) and the raid view only that raid's card. The model key is `merge_queues`.
- Drift findings for the default scope, grouped by rule, one block per project resolved from the parties shown (parties without a project are skipped). Each finding carries its owning `party` when known. The party and raid views keep only their parties' findings and hide findings with no party.
- A "projects" section (model key `projects`): one card per project of the parties shown, with `open PRs N/cap` and the `wait:` text of `guild next` when `max_open_prs` is reached, `hot files` touched by at least `max_open_prs_per_file` open PRs with their refs, `finding classes` with PR count and threshold marking classes at or above `finding_guard_threshold`, and `sdd synced Xm ago, tracker synced Ym ago`. Lists are hidden when the feature is off or empty. Each party also shows `open PRs N/cap` and its `wait:` text when `max_open_prs_per_party` is set (model key `caps`).
- One collapsible block per party with its own drift (same findings and cap of 5 as the session brief, then `N more`; hidden when empty), quests, tasks and PRs, plus PRs outside active tasks (legacy loose rows and PRs on queued tasks; adventurer PRs show under the adventurer), raids and claims.
- A state filter in the header (`all`/`fixes-main`/`fixes-flaky`/`needs-ask-answer`/`needs-human-pr-review`/`converging`/`ready`/`draft`/`merged`). The sidebar view narrows parties, asks and notices as `guild board --raid` does.
- The page re-fetches `/api/board` every 10 seconds and repaints only the sections whose data changed, so a form you are typing in keeps its text and focus. It also keeps the current filters and which blocks are collapsed.
- PR links open `https://github.com/<repo>/pull/<n>` in a new tab. PR cards show review pills (`N unresolved threads`, `changes requested`, `behind base`, `merge conflict`, the same reasons as the merge queue) and `on <base>` when the PR targets a branch other than `main` or `master`. A task links to its tracker card when the project configures `tracker.browse_url` (see [Configuration](configuration.md)).
- A "bases" section ([`guild base`](#guild-base)) and a collapsible "resources" section at the bottom ([`guild resources`](#guild-resources)).

**Colors.** CSS classes only (no inline style), with light and dark variants through `prefers-color-scheme`. Text labels stay, so color is never the only signal.

- PR lifecycle badge: `converging` amber, `ready` green, `draft` gray, `merged` purple, `closed` muted gray. The type is a neutral gray chip next to it.
- Urgency marks and human flags: `fixes-main` red, `fixes-flaky` blue, `needs-ask-answer` red, `needs-human-pr-review` amber.
- Checks: `✗N` red when N > 0 and muted otherwise, `✓N` green, `⏳N` amber when N checks are running, `no checks` muted when there are none.
- Merge queue entries in `waiting` state show their reason in amber. Task state: `active` blue, `blocked` red, `queued` muted.

**Notices from the page.**

- Every active notice card shows its time left (the model carries `expires_at` and a server-computed `time_left`) and a `seen` flag. Unseen cards get a `new` badge and a `Mark seen` button. Seen cards have no badge and a subtle `Mark unseen`. The heading reads `notices (N) · M new` and has a `Mark all seen` button. The model also carries `new_notice_count`.
- `POST /api/notices/<id>/seen`, `/unseen` and `POST /api/notices/seen-all` (body `{}`) run `guild notice seen`, `unseen` and `seen --all` as the human actor, with the same validation as the ask routes.
- A form creates a notice: text, a target select (`project:<name>` per project and `raid:<name>` per raid on the board) and a ttl select (1h, 8h, 1d, 3d). `POST /api/notices/create` (body `{"text": "<text>", "to": "<scope>", "ttl": "<dur>"}`) runs `guild notice create` as the human actor. Empty text, an unknown scope, a bad ttl and the length caps answer `422` with the message. `--until` is CLI-only for now.

**Answering from the page.** Each open ask card has one button per option (clicking only copies the option's text into the answer field), an answer field, an `Answer` button and a `Dismiss` button (which asks for confirmation).

- Answers and dismissals go through the same code as `guild answer` and `guild dismiss`, as the human actor. The same length cap, email and project `pii_patterns` rejection, "not open" and unknown-ask errors apply, and a rejected request shows the server's message under the buttons. `pii_patterns` are those of the project of the party that asked, wherever `guild web` (or `guild answer`) is started from.
- An empty answer is not sent. Buttons are disabled while a request is in flight. On success the board is re-fetched. The 10-second refresh keeps what you typed and the focus.

**Achievements and in-progress pages.** The board header links three pages, `board`, `in progress` and `achievements`. They share the CSS tokens and light/dark support, read `GET /api/history` (the same model as `guild history`, with optional `party`, `raid` and `project` query parameters), are read-only and render text with `textContent` only.

- `GET /progress` (`guild/web/progress.html`, script `guild/web/progress.js`): quests in progress as a table (party, quest, a `<progress>` bar with done/total tasks, start and time since last activity; "nothing in progress" when empty). A quest idle for longer than the project's `next.stale_hours` gets a `stale` marker (none when the key is absent).
- `GET /history` (`guild/web/history.html`, script `guild/web/history.js`): a totals strip (quests, PRs merged, tasks, asks answered with median, handoffs), then completed-quest cards (dates, duration, epic progress bar, SDD tasks, JIRA cards, PRs, handoffs, asks, accepted drift; legacy quests show a `no snapshot` badge and `—` for unknown fields), closed-without-completing cards (reason, tasks not done at marking time), finished-raid cards (duration, parties, quests, PRs, pauses) and a lifecycle-failures list (project, event, status, detail, last output line).

**Security model.**

- The server binds to `127.0.0.1` only, on the stdlib's `http.server.ThreadingHTTPServer`: no third-party dependency, no build step. Ctrl-C exits cleanly. It logs no per-request access noise to stderr (server errors still do) and writes nothing to the database except through the commands below.
- Reads are `GET`. The writes are:
  - `POST /api/asks/<id>/answer` (body `{"answer": "<text>"}`) and `POST /api/asks/<id>/dismiss`;
  - `POST /api/notices/<id>/seen`, `POST /api/notices/<id>/unseen`, `POST /api/notices/seen-all` (body `{}`) and `POST /api/notices/create`;
  - `POST /api/raids/<name>/pause` and `POST /api/raids/<name>/resume`;
  - `POST /api/parties/<name>/hand-off` (body `{}`);
  - `POST /api/revive`, `POST /api/parties/<name>/revive` and `POST /api/adventurers/<id>/revive` (body `{}`);
  - `POST /api/quests/create-open`, `POST /api/quests/<slug>/take` and `POST /api/quests/<slug>/release`;
  - `POST /api/prs/<owner>/<repo>/<n>/block` (body `{"reason": "<text>"}`) and `.../unblock`;
  - the idea, base and other routes listed in their sections.
  `<id>` and `<n>` are positive integers (otherwise `404`). Every other method, including `OPTIONS`, is `405`, and no response carries CORS headers, so cross-origin preflights fail.
- Requests whose `Host` is not exactly `127.0.0.1:<port>` or `localhost:<port>` get `421`, which blocks DNS rebinding.
- A `POST` must also pass all of: an `Origin` header equal to `http://127.0.0.1:<port>` or `http://localhost:<port>` (`403`); an `X-Guild-Token` header equal to the session token, compared in constant time (`403`); `Content-Type: application/json` (`415`); a `Content-Length` of at most 16384 bytes (`411` when missing, `413` when larger, exactly that many bytes are read); and a JSON object with the required string key (`400`).
- The token is generated with `secrets.token_urlsafe(32)` and stored in `<state dir>/web-token` with mode `0600`. Restarts reuse it, so an open tab keeps working; delete the file to rotate it at the next start. A file with invalid content or a symlink is replaced by a fresh token. The token is never logged and is printed only in the URL fragment. The page reads it from the fragment, keeps it in `sessionStorage` for that tab, removes it from the address bar and sends it in `X-Guild-Token` on every `/api` request. It never uses `localStorage` or a cookie. Every `GET /api/*` without a valid token answers `403`. The HTML and static files stay public. There is no `/api/session` endpoint (`404`). A custom header cannot be sent cross-origin without a preflight, which is refused.
- An unexpected error answers a generic `500` `{"error": "internal error"}`. Validation failures answer `422` with `{"error": "<message>"}` and never echo the submitted text.
- Every response carries a strict `Content-Security-Policy` (`default-src 'self'`, no inline or third-party scripts, no external assets), `X-Content-Type-Options: nosniff` and `Referrer-Policy: no-referrer`. `/api/*` also sends `Cache-Control: no-store`.
- The page (`guild/web/app.js`) builds every node with `document.createElement` and sets text with `textContent` only. It never uses `innerHTML` or any HTML-injecting API, so text from agents, SDD, GitHub or the tracker is never executed.
- Every write runs a command function of `guild/commands` as the human actor, the one behind the CLI command (`ask.answer`, `ask.dismiss`, `notice.mark_seen|mark_unseen|mark_all_seen`; for a PR, `pr.block_external` and `pr.unblock_external`, which record `pr set --blocked-external` with no party; an empty reason or an untracked PR answers `422`).

## History and maintenance

### `guild history`

Read-only record of what the guild has achieved.

```
guild history [--party <name>] [--raid <name>] [--project <name>]
```

`--party`, `--raid` and `--project` narrow every section except lifecycle failures (narrowed by `--project` only, since a lifecycle run has no party). They combine. Six sections:

1. In progress: quests whose projection state is `active`, newest first (undated last), with party, project, epic, start, age, task counts (done, active, blocked, queued) and percent done. Quests finished by `guild party close` leave this list.
2. Completed quests, newest first. Each shows party, project, epic progress, start, end and duration, tasks done, JIRA cards done, PRs merged, handoffs and ask metrics, read from the `achievement` snapshot frozen in the `quest.done` event. Quests closed before snapshots existed are derived from events and marked `no snapshot`.
3. Closed without completing: quests flagged with `guild quest incomplete`, newest first, with title, party, dates, reason and how many tasks were not done at marking time. They do not count in totals or in finished raids.
4. Finished raids, newest first: raids with no active member, derived from `raid.joined`, `raid.left` and `party.closed` events and membership expiry. Each shows start (first join), end, parties, quests completed and PRs merged by member parties inside that window, and the pause count.
5. Lifecycle failures, newest first: failed, timed-out and errored `lifecycle.ran` events with project, event, status, exit detail and the last non-empty output line.
6. Totals: quests done, PRs merged, tasks done, asks answered, median ask answer time, handoffs.

### `guild cost`

Reports token usage per session, party, model, quest or task, from the Claude Code transcripts.

```
guild cost [--since <dur>] [--by session|party|model|quest|task] [--project <name>]
```

```
guild cost --since 3d --by party
party      input  cache write  cache read  output
beta       0.004        1.820      96.310   0.211
unbound    0.001        0.310       8.402   0.020
total      0.005        2.130     104.712   0.231
```

- `--since` takes a duration and keeps days from that date on. `--by` defaults to `session`. `task` shows `quest/tid`. `--project` keeps samples of parties in that project (unbound usage has no project and is excluded).
- Values are millions of tokens with three decimals, ordered by total descending. With nothing to show it prints `no cost data`.
- Each run first collects new usage from `~/.claude/projects/*/<session>.jsonl` and `*/<session>/subagents/agent-*.jsonl`, then prints the table.
- It reads only `message.usage`, `message.model`, the line `type`, its `timestamp` and `message.id`. The id is used only to dedupe and the timestamp only to bucket by UTC day and task window. Nothing else is stored.
- Collection is incremental: a byte-offset cursor per transcript (`transcript_cursors`) means a re-run reads only what was appended. A line without a trailing newline is not consumed until complete. Lines newer than a 10-minute grace are left for the next run. A file smaller than its cursor restarts from the beginning. Streamed chunks of one message id count once, with the highest value of each usage field.
- Each run records one `cost.sampled` local event per session, UTC day, model, party, quest and task, holding only the increment since the last run, and only when it is non-zero. The `cost_samples` projection sums them and `guild rebuild` reproduces it. The cursors are not rebuilt.
- Attribution: the session maps to a party through the latest event of that session that carries a party. A message belongs to a task when its timestamp falls inside a window that opens at `task.started` and closes at the next `task.blocked` or `task.done` of the same task (open-ended if none). When windows overlap the latest start wins. Everything else has no task, shown as `-`. Subagent transcripts count under their parent session.
- Limitations: usage recorded before a session is bound is `unbound` and is not reattributed. There is no pricing, only token counts.

### `guild compact`

Shrinks the database without changing any projection. Every sync appends a full snapshot to the event log even when nothing changed, so the database would grow without bound.

```
guild compact [--dry-run]
```

- It keeps only the two newest `epic.synced` events per project and epic and the two newest `tracker.synced` events per project. Each is a full snapshot that replaces the previous one, and the second newest stays as the last known change.
- For each run of consecutive identical `pr.synced` events (per PR, ignoring `synced_at`, broken by any other `pr.*` event of that PR) it keeps the first and the last. So `guild rebuild` gives the same projections and the board freshness does not move.
- It deletes `resources.sampled` events and the `resource_samples` and `resource_machine` rows older than the global `resource_retention_days` (90 when absent), and the per-session files under `$XDG_STATE_HOME/guild` (`ctx/`, `ctx-baseline/`, `background/`) not touched for 30 days.
- Before deleting, it copies the database with SQLite's online backup to `$XDG_DATA_HOME/guild/guild.db.pre-compact`, overwriting the previous copy. If the copy fails nothing is deleted. After the deletes it records one local `db.compacted` event and runs `VACUUM`, which needs free disk of about the database size and fails with a clear error if the database is locked (the deletes are already committed then).
- `--dry-run` prints what would be deleted and neither backs up nor changes anything.
- A second `compact` while one runs prints `compact already running`. The background job runs it at `Nice=19`. On a large database it blocks writes for about a minute, so run it when idle. Readers keep working.
- Web: the "resources" section has a "Compact db" button (`POST /api/compact`, same function). Next to it, "Collect now" posts to `POST /api/resources/collect` and runs `guild resources collect`.

### `guild resources`

Shows per project how much disk the repo occupies and how it grew, so a repo filling the machine is noticed before the disk is full. It measures and reports. It never deletes, cleans or alerts (cleanup belongs to the lifecycle commands), does not measure per-container or per-process memory and has no thresholds.

```
guild resources collect
guild resources [--project <name>] [--since 1d]
```

- `collect` records history. The report only reads it. The background job runs `collect` every 2 hours at `Nice=19`.
- The report compares the latest sample of each project with a baseline: the newest sample at or before `--since` (default `1d`) or, if none is that old, the oldest one, marked `(oldest available)`. With a single sample there is no baseline and no deltas.
- Per category it shows the total and delta and the 10 biggest items (`+N more` for the rest). An item absent from the baseline is `new`. `top growers` lists up to 5 items that grew at least 1 MiB (a new item counts with its whole size).
- The `machine` line shows disk use, memory available, CPU load per core (1-minute load over the core count, with the 15-minute load), Docker totals, the database size and the sample age. `untracked growth` appears when the disk grew at least 1 GiB more than every tracked delta together.

```
machine   disk 82% used (412.0 GB of 500.0 GB, +6.0 GB in 1d)   ram 9.0 GB available of 31.0 GB   cpu 1.8/core (load 7.2 on 4 cores, 15m 6.1)
          docker 17.4 GB (reclaimable 5.2 GB)   guild.db 173 MB   sampled 41m ago
untracked growth: +1.4 GB (machine +6.0 GB, tracked +4.6 GB)

acme   total 9.7 GB (+4.4 GB)   baseline 2026-10-02 09:00 (sampled 41m ago)
  worktree           7.3 GB (+2.1 GB)
    /home/u/acme/app                            4.1 GB   +300 MB
    /home/u/acme/app/.claude/worktrees/feat-x   3.2 GB   +1.8 GB   merged, still on disk
  docker_image       2.3 GB (+2.2 GB)
    acme-feat-x-web:latest                      2.3 GB   +2.2 GB   orphaned
  top growers: acme-feat-x-web:latest +2.2 GB, feat-x +1.8 GB, app +300 MB
```

**What is measured.**

| Category | Source | Attributed to |
| --- | --- | --- |
| `worktree` | `du -s -B1 -x` of each clone and `git worktree list` entry, excluding worktrees nested inside it | the project whose clone lists it |
| `docker_container` | writable layer of each container | compose working directory label |
| `docker_image` | unique size of each image | its containers, else the compose project name prefix |
| `docker_volume` | size of each volume | compose project label |
| `claude_scratch` | `/tmp/claude-<uid>/<encoded cwd>/...` | the checkout whose encoded path matches |
| `claude_transcripts` | `~/.claude/projects/<encoded cwd>/...` | the checkout whose encoded path matches |
| `docker` | marker row, only when Docker cannot be read | unattributed |

- Machine totals are stored with every sample: disk used and total of `/`, memory total and available, Docker totals (images, reclaimable images, containers, volumes, build cache) and the size of the guild database with its `-wal` and `-shm` files. Build cache is machine-level only.
- Attribution: a checkout directory name is encoded like Claude Code does (`/home/u/app` becomes `-home-u-app`) and matches the directories whose name is that or starts with it plus `-`. When several checkouts match, across all projects, the longest path wins.
- Docker objects follow the labels `com.docker.compose.project` and `com.docker.compose.project.working_dir`. A container goes to the project whose checkout or `paths` prefix contains the working directory (longest wins, a tie goes to the first project by name). A volume follows the working directory of its compose project, or a worktree whose name matches the compose project. An image follows the containers that use it when they agree, else the longest compose project name that prefixes its repository. What cannot be attributed goes to `unattributed`. Image size is the unique size, so shared layers are not counted per image and the sum is approximate.

**Flags** are computed at collect time and stored with the sample:

- `merged, still on disk` and `closed, still on disk`: the latest PR of the worktree's branch is merged or closed. The main checkout and detached worktrees are never flagged.
- `orphaned`: the compose project's working directory no longer exists, or it has no container and no checkout whose name matches it.
- `dangling`: an image with no repository. `unused`: an unattributed image no container uses (dangling wins).

**Unavailable and slow parts.** Nothing that cannot be measured stops a collect or becomes a zero. An item that could not be read is `unavailable`, one whose `du` hit the 300 s limit or arrived after the 20 minute whole-run deadline is `skipped`, and a vanished worktree is `missing`. All store null bytes, show as `?` and are left out of totals and deltas. Docker failures record a `docker` marker with the reason (`not installed`, `permission denied`, `daemon unreachable`, `timeout`, `unparseable`).

- The summary line, for example `sampled 4 projects, 87 items in 94s; unavailable: docker (permission denied); skipped: 2`, exits 0 unless there are no projects or the write fails.
- A collect that finds another one running prints `collect already running` and exits 0 (lock `$XDG_STATE_HOME/guild/resources/collect.lock`).
- Sizes are measured one at a time with `du`, which can take minutes on large trees, hence the low priority. All measuring happens before a single write transaction records every event, so the database is never locked while `du` or Docker runs.
- Each collect adds one `resources.sampled` local event per project plus one for unattributed items, roughly 3 KB each, about 30-40 MB a year at the recommended cadence. `guild compact` deletes samples older than `resource_retention_days`.
- Privacy: collection is read-only and runs a fixed argv with no shell and a timeout. Nothing from a project config is executed. Samples hold local paths, branch names, Docker object names and byte counts, as local events that are never exported. Of a container only its name, size, compose project name and working directory are read: no commands, environment or other labels.

**Web.** The board has a collapsible "resources" section built from `GET /api/resources[?project=<name>&since=<dur>]` (default `since=1d`), the same model as the CLI: `machine`, `projects` and `unattributed`, each with categories, items, growers and the baseline. An unknown project or invalid window answers 422. It is not part of `/api/board`, and every category and flag has a tooltip. The web shows coloured pills (disk green under 70%, amber under 85%, red above; RAM red under 10% available; CPU load per core amber from 0.8, red from 1.5; growth amber, shrink or no change green; unmeasured values grey) and a disk pill in the sidebar. The report itself has no thresholds.

### Hooks and session plumbing

Hooks are run by Claude Code and git, not by hand. See [Hooks](hooks.md) for what each does.

```
guild hook session-start   # reads Claude Code hook JSON on stdin
guild hook prompt-submit
guild hook post-tool-use
guild hook pre-push
guild hook pre-pr-owner
guild hook pre-answer
guild hook pre-edit
guild hook pre-commit      # git hook: no stdin, session from CLAUDE_CODE_SESSION_ID
guild hook notification    # records the session status
guild hook stop
guild hook stop-failure    # records waiting-limit on a rate-limit or billing error
guild hook subagent-start  # marks a running subagent
guild hook subagent-stop
guild hook pre-compact     # records the context percentage before an automatic compaction; bound sessions get summary instructions
guild inbox --since-last
guild statusline --session <id> [--ctx <pct>]   # bound: [⚔ <raid>[ ⏸], ...] · g<N> · ⚑<n> asks · <n> notices · ⏸<n> blocked
```

### Data commands

```
guild seed <file.json>
guild rebuild
guild export --visibility guild
```

- `seed` writes events from a JSON file. `rebuild` drops the projections and replays the events. `export --visibility guild` exports the guild-visible events. See [Data](data.md).
