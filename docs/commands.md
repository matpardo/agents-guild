# Commands

Back to the [README](../README.md).

## Commands

`guild --help` lists every command with a one-line description. `guild <command> --help` shows its subcommands and flags. This section is the full reference.

```
guild whoami
guild doctor [--scan-prs]   # read-only checks: hooks, permission rules, GUILD.md, project configs; --scan-prs: guild traces in open PRs
guild init-project <name> --config <file.json>
guild wire-settings   # merge guild hooks and permission rules into ~/.claude/settings.json
guild unwire-settings   # remove guild hooks and permission rules from ~/.claude/settings.json

guild party start <name> --reason "<why>" --goal "<what it is for>" --done-when "<condition that ends it>"   # no permission prompt; refused while this session leads another active party
guild party resume <party> [--session <name>]   # --session: from a human terminal only
guild party set <party> [--goal "<text>"] [--done-when "<text>"]   # change the goal or the done condition (at least one); also the Edit goal button on the web party card
guild party park <party> --reason "<what it waits on>"   # human terminal or web: mark a party as waiting on something outside development
guild party unpark <party>   # clear the mark; a session resuming the party clears it too
guild party close [<party>] --pending "<text>" [--force]  # <party>: from a terminal, or your own party; --pending none when nothing is left; --force overrides the quest done gate and the open ask and PR check

guild quest add <slug> --title "..." --epic <slug> [--tasks T09,T07b] [--reason "<why>"]   # without --tasks: an empty epic quest; --reason is optional on every quest add
guild quest add <slug> --title "..." --no-epic [--tasks A,B [--titles "First,Second"]]
guild quest add <slug> --title "..." --followups-of <quest> [--tasks A,B [--titles ...]]
guild quest add <slug> --open --title "..." (--epic <slug> --tasks T09 | --no-epic --tasks A,B --titles "First,Second")   # open quest no party owns; works with no session
guild quest take <slug>      # your party takes an open quest of its project
guild quest release <slug>   # owner party returns a quest with only queued tasks to the board
guild quest board [--project <name>]   # open quests and the synced SDD tasks no quest covers
guild quest done <slug> [--accept-drift] [--force]   # refuses while tasks are not done; --force overrides
guild quest incomplete <slug> --reason "..."          # a done quest that was not really finished

guild task add <quest>/<tid> --title "..." [--reason "<why>"] [--no-sdd]   # open quests of your party, epic quests included
guild task start <quest>/<tid> [--summary "..."]
guild task block <quest>/<tid> --reason "..."
guild task done  <quest>/<tid> [--summary "..."]   # epic quests: also mark it done in the epic's tasks.md
guild task move  <quest>/<tid>[,<tid>...] --to <quest>   # queued or blocked tasks, same epic, to another party's quest or an open quest
guild task discard <quest>/<tid> --reason "..." [--force]   # drop a task created by mistake; never use `done` for it
guild task restore <quest>/<tid>                   # a discarded task comes back as queued

guild pr track <owner/repo>#<n> --task <quest>/<tid> [--card <KEY>] --what "..." --waits "..." [--needs-human-pr-review]
                               # a party needs --task; an adventurer needs --task equal to its own; a health-job adventurer passes no --task, --card optional
                               [--fixes-main] [--fixes-flaky]
guild pr set   <owner/repo>#<n> [--lifecycle draft|converging|ready] [--waits "..."]
                               [--needs-ask-answer | --no-needs-ask-answer]   # manual override; an open ask on the PR also counts
                               [--needs-human-pr-review | --no-needs-human-pr-review]
                               [--fixes-main | --no-fixes-main]
                               [--fixes-flaky | --no-fixes-flaky]
                               [--blocked-external "<reason>" | --no-blocked-external]
                               [--task <quest>/<tid>] [--card <KEY>]   # relink: the PR's own party or adventurer only; a party's task must be one of its own
guild pr untrack <owner/repo>#<n>   # stop tracking: drops the PR row and its drift findings; own PR only
guild pr ready-check <owner/repo>#<n>   # refreshes the PR from gh, then lists everything standing between it and a merge; fails while review comments are unread
guild pr ack <owner/repo>#<n>   # mark the PR's review comments as read
guild pr wait <owner/repo>#<n> [--timeout <dur>]   # block until a comment or review by another author, checks finished, merge or close; exit 0 on a change, 3 on timeout, 4 when no sync ran for 30m

guild finding list                              # finding classes of the project with PR counts
guild finding record <owner/repo>#<n> --class <slug>   # count a recurring audit/review finding class once per PR; with finding_guard_threshold set, one project notice asks for an architecture guard when the class repeats that many times

guild ask "<question, at most 300 chars>" --context "<at most 2000 chars>" [--ref <ref> ...] [--option "..."] [--recommend "<option and why, at most 300 chars>"]   # prints a warning, and still creates the ask, when question or context carry many ids or paths; refs: pr:<owner/repo>#<n>, task:<quest>/<tid>, card:<KEY>; with exactly one task in progress and no task:/card: ref it is added for you
guild ask wait <id> [--timeout <dur>]   # block until the ask is answered or dismissed; exit 0 on either, 1 on an unknown id, 3 on timeout (default 2h)
guild answer <id> "<text>"
guild dismiss <id>                  # both refuse inside a Claude Code session: run them from the human terminal or the web board
guild asks [<id> | --all [--party <name>] [--since <dur>] | --answered [--page <n>] [--party <name>] [--since <dur>]]   # open asks; <id> shows recommendation, task, card, PR, then SDD paths and resume command under `dig in`; --all adds answered and dismissed with answers

guild notice create "<text>" --to project:<name>|guild|raid:<name> --ttl <dur> [--until pr:<owner/repo>#<n>:merged|closed]
guild notice close <id>
guild notice seen <id>|--all
guild notice unseen <id>
guild notices

guild idea add "<title>" --description "<text>" [--requester <text>] [--deadline YYYY-MM-DD] [--project <name>]
guild idea edit <id> [--title ..] [--description ..] [--requester ..|--no-requester] [--deadline ..|--no-deadline] [--project ..|--no-project]
guild idea delete <id>
guild idea link <id> [--party <name> | --adventurer <id>]     # a session links itself (party or adventurer); the human terminal needs one flag
guild idea unlink <id> [--party <name> | --adventurer <id>]   # refused once the party or adventurer tracks a PR
guild ideas [<id> | --project <name>] [--exported]   # sorted by deadline, no deadline last; overdue marked; <id> shows one in full; --exported lists the exported ones
guild idea export (<id>... | --project <name>) --to <destination> --out <file.md>   # human only; the ideas leave the list
guild idea unexport <id>                         # human only; brings an exported idea back
guild idea import <file.md> --receipt <receipt.md> [--project <name>]   # human only; writes the receipt
guild idea confirm-export <receipt.md>           # human only; deletes the exported ideas the receipt confirms

guild adventurer start "<job>" --task <epic>/<tid> --reason "<why>"   # this session becomes an adventurer; no permission prompt; --task required
guild adventurer start --job <name> --reason "<why>"    # the same for a health job of the project config; no job text, no --task
guild adventurer promote <party> --reason "<why>" --goal "<text>" --done-when "<text>"   # the active adventurer becomes the leader of a new party; its PRs move to it
guild adventurer launch <name>                          # human terminal only: tmux window running a health job in the project's first path
guild adventurer done --pending "<text>"                # ends it; `--pending none` is the explicit empty report
guild adventurer dismiss <id>                           # removes a done adventurer, or an active one whose session is gone, from the board
guild adventurers [<id>]                                # active ones newest first, then recent done ones; <id> shows one in full
guild solo list [--project <name>]                     # solo players of the project config with trigger and state
guild solo status [<owner/repo> <job> | --project <name>]    # same rows as list; one player adds its last 5 runs and 10 channel messages
guild solo launch <owner/repo> <job> | --all | --project <name>  # human terminal only: tmux window running a solo player, due or not
guild solo stop <owner/repo> <job> | --all | --project <name>    # human terminal only: close the window, dismiss the run and pause the player
guild solo resume <owner/repo> <job> | --all | --project <name>  # human terminal only: lift the pause
guild solo tick                                         # background job: launch every due solo player (human terminal only)
guild solo say "<text>"                                 # solo player session only: post an important message to the channel (max 300 chars)
guild solo channel [--limit N] [--project <name>]     # latest solo channel messages, newest first (default 20)
guild solo runs <owner/repo> <job>                      # last runs of a solo player: start, state, duration, pending

guild claim <area> --ttl <dur>          # area, or task:<epic>/<tid> / task:<quest>/<tid>
guild claim check <area>                # read-only, no event; exit 0 free/yours, exit 1 someone else's
guild release <area>
guild claims

guild memory add "<text>"                     # your bound party's memory; requires binding
guild memory list [--party <name>]            # read-only; no party: every known party
guild memory rm <party>/<seq>                 # bound session: only your own party; unbound (terminal or web): any party

guild raid join <name> --ttl <dur>      # the caller's bound party joins; joining again refreshes the TTL
guild raid join <name> --until-leave    # joins with no expiry; ends only on `raid leave` or `party close`
guild raid leave <name>
guild raid pause <name>               # any active member or the human: ask every member party to stop
guild raid resume <name>              # lifts the pause and posts a notice to raid:<name>
guild raids
guild base pause|resume <owner/repo>   # stop or restart the bases fetch of a repo

guild next [--all]     # ranked action queue for the caller's party
guild handoff --in-flight "..." --learned "..." [--parked "<what it waits on>"] [--model <m>] [--respawn] [--close]
guild handoff prune [--dry-run]
guild handoff --party <name>   # terminal only: hand off a party whose leader session is gone

guild merge-queue [--raid <name> | --party <name>]   # read-only: PRs in the order to merge by hand
guild merge-queue --head [--raid <name> | --party <name>]   # the first PR whose action is merge or review: <ref> <party> <task>
guild merge-queue pin   <owner/repo>#<a> --before <owner/repo>#<b>
guild merge-queue unpin <owner/repo>#<a> --before <owner/repo>#<b>
guild review-md [--raid <name> | --party <name>]   # read-only: markdown list of the PRs ready for the person, in queue order
guild main red <owner/repo> --reason "<text>"   # mark a repo's main branch red by hand
guild main green <owner/repo>                   # clear the manual red mark

guild history [--party <name>] [--raid <name>] [--project <name>]   # read-only: in-progress quests, completed quests, quests closed without completing, finished raids, totals
guild cost [--since <dur>] [--by session|party|model|quest|task] [--project <name>]   # token usage from Claude Code transcripts, in M tokens
guild resources [--project <name>] [--since <dur>]   # read-only: what each project costs the machine in disk, with growth since the baseline
guild resources collect                                # measure and record a resources.sampled event per project
guild board [--party <name> | --raid <name>]
guild web [--port <n>]   # local board in a browser: board, in-progress and achievements pages
guild sync --source gh|sdd|tracker|bases [--all-projects]   # --all-projects: every project config (sdd and tracker)
guild lifecycle run on_pr_merged|on_pr_closed [--repo <owner/repo>] [--dry-run]   # run a project's lifecycle command by hand
guild drift [--epic <slug> | --all]
guild revive [--party <name> ...] [--all] [--list]   # relaunch active or handed-off parties
guild brief [<party>/<quest>/<tid>]   # no argument: per-session view; with a task: read-only, budgeted brief for a fresh session
guild inbox --since-last
guild statusline --session <id> [--ctx <pct>]   # bound: [⚔ <raid>[ ⏸], ...] · g<N> · ⚑<n> asks · <n> notices · ⏸<n> blocked

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
guild hook subagent-start  # marks a running subagent
guild hook subagent-stop
guild hook pre-compact     # records the context percentage before an automatic compaction; bound sessions get summary instructions

guild seed <file.json>
guild rebuild
guild compact [--dry-run]   # back up the database, drop duplicate sync events and old resource samples
guild export --visibility guild
```

Refs use three literal formats: `pr:<owner/repo>#<n>`, `task:<quest>/<tid>` and `card:<KEY>`.
Durations: `30m`, `8h`, `3d` — anything else is rejected.

### Ask ordering

`guild asks` and the board summary sort open asks by how many of their refs
are still blocked *right now*, computed at render time (not by the raw
number of refs): blocked count desc, then `created_at` asc, then id asc. A
`pr:` ref is blocked while the tracked PR's lifecycle is not `merged`/
`closed`; an untracked PR ref counts as blocked (we can't know, and never
assume done). A `task:` ref is blocked while that quest task's state is not
`done`; an unknown task ref counts as blocked. The board summary line adds
`· blocks <n>` when `n > 0`; `guild asks` prints `blocks: <n> of <total> refs
still open`, or `blocks: 0 of <total> refs still open (may be stale)` when
every ref has resolved — a hint the ask can probably be dismissed. A `card:`
ref never counts as blocked.

### Ask context

A `card:<KEY>` ref is accepted when the key is in the synced `cards` of the
asking party's project or fully matches that project's `sdd.key_ref`.

When an ask is created guild stores a snapshot of its origin: session id and
name, the party's in-progress tasks, their epics, the card keys of the party's
PRs and of those tasks, and the latest handoff file. With no `task:` or `card:`
ref and exactly one task in progress, `task:<quest>/<tid>` is added and
`auto-ref: task:<quest>/<tid>` is printed. With no ref and no single in-progress
task the ask is refused. `--context` stays required to create an ask.

`--recommend` states the option the agent recommends and why. `--context`,
`--recommend` and the answer render paragraphs (blank line), line breaks and
`**bold**` in the CLI and the web; nothing else is interpreted.

`guild asks <id>` expands the ask in two tiers. First what decides it: question,
context, options, recommendation, and the task with its state, the card with its
status and tracker link (`tracker.browse_url`), the PR with URL, lifecycle and
checks. Then `dig in`: the task SDD spec and tasks paths (from the project `sdd`
block: the filesystem path with `root`, or `git:<ref>:<path>` with
`git_repo`/`git_ref`), the origin snapshot and the command that resumes the
asking session; on the web `dig in` is closed by default. Asks created before snapshots print `origin: not recorded`. The same
detail is served at `GET /api/asks/<id>` and opens from the `detail` control of
each ask on the web board.

`guild asks --all` lists open, answered and dismissed asks in id order, with the
answer and answer time (local `YYYY-MM-DD HH:MM`) of answered ones; `guild asks <id>` shows creation, answer and event times in local time too. `--party` and `--since` (on
`created_at`) narrow it and need `--all` or `--answered`; `<id>` takes no filters.

`guild asks --answered` lists only answered asks, newest answer first, 10 per page
(`--page <n>`), each with its party, answer and answer time. The web board shows the
same list in a collapsed "answered asks" section under the open asks, served at
`GET /api/asks/answered?page=<n>`.

### `guild next`

Deterministic, per-party ranking, evaluated in order:

1. Own PR marked `fixes-main` or `fixes-flaky`: it unblocks every party, so it
   comes before the caller's own problems, healthy or not
   (`fixes a broken main — land it first`). A PR listed here is not listed
   again by the rules below.
2. Own PR with failing checks (not when they are all billing failures,
   `prs.checks_billing`), a merge conflict (`mergeable == CONFLICTING`),
   or unseen review comments (`review_comment_count >
   last_notified_comment_count`).
3. Own PR carrying the manual `needs-ask-answer` flag that has an ask,
   referencing it, answered after the PR was last `pr set`. A PR blocked only
   by an open ask needs no step here: answering the ask unblocks it.
4. Own PR `converging` with no activity for longer than the project's
   `next.stale_hours` (skipped entirely when that key is absent — no hidden
   default).
5. Own tracker or SDD drift (`PR open, card not started`, `PR merged, card
   not done`, `task started, card not started`, `task done, SDD not done`),
   one `update tracker/SDD: <finding>` line per finding, after the PR
   attention above and before the next task. Reads the DB only; guild never
   writes to the tracker or the SDD.
6. Open-PR caps: when the project sets `max_open_prs_per_party` and the
   caller's party already has that many open (not merged, not closed) tracked
   PRs, no new task is offered; the line is `wait: <n> open PRs, merge <ref>
   first`, naming the party's first PR in merge-queue order. Then, when the
   project sets `max_open_prs` and all parties of the project together have
   that many open tracked PRs, the line is `wait: <n> open PRs in project,
   merge <ref> first`, naming the first PR of the project-wide queue. Absent
   keys → no cap. PRs blocked manually (directly or through a queue
   predecessor) are not counted by either cap.
   After the caps, WIP 1: while an own tracked PR that is Ready for review is
   not human-ready (its `human` state in the merge queue is `waiting` or
   `blocked`), no new task is offered; the line is `wait: <ref> is not
   human-ready (<what is missing>), resolve it first`. Drafts, `converging`
   PRs, PRs blocked manually, PRs that only wait for the CI label
   (`ready (CI pending)`) and PRs in a project without `human_ready.ci_label`
   whose only missing item is `no checks on head` do not count. A party held
   this way still counts as having work (`stopped-with-work`, `queued`). No config key.
   Whether a new task would touch files an open PR already changes is not
   checked: a task's files are unknown before work starts.
7. Next queued task of the caller's active quests, ordered by the observed
   `tasks.order_idx` (nulls last, then `tid`), whose dependencies (`tasks.deps`)
   all resolve `done` (see resolver below), that has no open ask referencing
   it and is not task-claimed by another party.
8. Nothing actionable: the exact blockers (pending deps and who says so, open
   ask ids, claim holders).

Any disagreement the dependency resolver finds between sources it consulted
is always printed as a `disagreement: ...` line, whether or not it changed
the outcome.

Without `--all`, only the single top item is printed; if it is a PR selected
because of new review comments, `guild next` also fires
`pr.comments_acknowledged` for it (documented side effect — the PR's
`last_notified_comment_count` catches up so the same comments are not
reported again). `guild next --all` prints the full queue and is always
read-only: it never fires that event.

### Closing a party

`guild party close` closes the caller's party; `guild party close <party>`
closes any party from a terminal (a session may only name its own party).
Close applies the `guild quest done` gate to each active quest of the party: it
refuses, listing every quest with tasks not done or epic drift, and `--force`
closes anyway, reporting each such quest as `closed with unfinished work`.
Close also refuses while the party has an open ask or an open tracked PR (with
its unseen review comment count), listed together with the quest problems in one
message; `--force` dismisses the asks and lists the PRs as still open. Closing
unbinds the session and a closed party cannot be resumed, so answer the asks and
merge or close the PRs first.
Before judging drift, close refreshes the SDD snapshot once per project with an
`sdd` block, as `guild sync --source sdd` would.

`--pending "<text>"` is required: it says what is left pending (`none` when
nothing is). The text goes through the same email, secret and project-pattern
checks as `handoff --learned` and is stored on the `party.closed` event. The
web board has no party close action.
After the close line, close prints a final report block read from existing
state: each PR the party tracked (`<repo>#<n> | what | state`, state `merged`,
`closed` or `open`), each quest with its done/total tasks, the ideas linked to
the party, then what the party generated: its asks with their state
(`ask #<n> (<state>): <question>`), the ideas it created and did not link
(`idea #<n> created: <title>`), the open quests its leaders added
(`open quest <slug>: no party yet | taken by <party>`, or `quest <slug> done`) and its notices still in
force (`notice #<n> (until <time>): <text>`), and last the pending text. The tracked PRs are refreshed from GitHub first;
if that fails the report keeps the last synced states and says so. The session ends with a report to the human
built from it.
Closing cascades in the same event: the party's active quests become `done`,
its open asks are dismissed and its claims are released. Tracked PRs stay
tracked for history and are listed if still open. `guild quest done <slug>`
finishes one quest without closing its party. It refuses while the quest has tasks
that are not `done` (queued, active or blocked), listing them; `--force` finishes anyway,
and the achievement snapshot still records reality (`tasks_done` counts only done tasks).
Quests without tasks are allowed. For an epic quest it first refreshes the SDD
snapshot of the project (as `guild sync --source sdd`, when the project has an `sdd`
block); if the refresh fails it keeps the stored snapshot and the refusal says it may be
stale. It then runs the drift check (the `guild drift` rules, scoped to that epic) and refuses with the
findings listed, split into `yours:` and `other parties:` (each with its party);
`--accept-drift` finishes anyway and records the findings. A quest whose tasks are all
done but whose epic has drift shows `can't close: drift (N yours, M other parties)` with
the same split on the text board and the web board. No-epic quests skip the gate. The `quest.done` event freezes an `achievement` snapshot
(started_at, done_at, party, project, epic, title, tasks_done, tasks_blocked_events,
sdd_tids, epic_progress, jira_cards_done, prs_merged, handoffs, sessions, asks_raised,
asks_answered, median_answer_seconds, drift) because the epic, card and task
projections are replaced on every sync. Closed parties leave the board
and quests that are `done` leave `guild drift`'s default scope.

### Marking a done quest as incomplete

`guild quest incomplete <slug> --reason "<text>"` records that a quest marked `done`
was closed without being completed. Only the owning party can run it, only on a quest
that is currently `done`, the reason is required and a quest can be marked once. It
appends a local `quest.marked_incomplete` event `{slug, reason}`; events are never edited,
and the quests projection is left untouched. `guild history` derives the flag from the
event: the quest leaves "Completed quests" and totals, and appears under "Closed without
completing" with title, party, dates, reason and how many tasks were not done when it was
marked. The event is local, so `guild export` skips it; `guild rebuild` replays it as a
no-op on the projections.

### Task done resolver

`guild next`'s dependency check resolves whether a task is done by asking,
in this fixed precedence order, the first source that has an opinion:
**guild** (any `quest_tasks` row for that epic/tid — `done` state means
done, any other state means not done), **tracker** (the card whose key the
task carries, from the last `guild sync --source tracker`: status category
`done` means done, `new`/`indeterminate` means not done; no key or no synced
card → no opinion), **sdd** (`tasks.sdd_status`). The tracker's status
category is used instead of status names, so it works in any tracker
language without a configured list. No opinion anywhere → not done, never
assumed done. When more than one source has an opinion and they disagree,
the disagreement is returned and surfaced by `guild next`.

### Session-start drift

The per-session `guild brief` (and so the session-start hook) lists the
caller's own tracker and SDD drift under a `drift:` header: the findings of
the four rules `guild next` ranks, for the caller's party only, capped at 5
with `N more: guild drift` after them. Nothing is printed without drift.

### `guild task start` nudge

When the started task's SDD card is still `new` in the tracker,
`guild task start` adds a `move <KEY> to In Progress` line to its output.

### Merge notices (`sync --source gh`)

When `guild sync --source gh` observes a tracked PR whose lifecycle flips to
`merged` during that sync (it was not `merged` before — a PR already merged
at `pr track` time does not count, since `pr track` never inspects
`mergedAt`), it posts one notice per raid the PR's owning party is currently
an active member of. The notice's author is the owning party, so the owner
never receives its own notice back while every other member does (same rule
as every other notice). The notice's TTL is a fixed 12h and its text is:

```
<repo>#<n> merged in main (<quest>/<tid>: <what>). Parties with open branches: rebase.
```

When the PR's linked card is not done, or its SDD task is not marked done,
the notice ends with `Owner follow-up: move <KEY> to Done; mark <tid> done in
<epic> tasks.md.` (only the parts that apply).

A PR tracked with `--card` (an adventurer's, or a legacy party row) shows `<card>: <what>` in place of `<quest>/<tid>: <what>`;
a PR with neither (seeded) shows just `<what>`.

If the project config has a `shared_areas` key (globs relative to the repo
root, matched with `fnmatch`) and the owning party is in at least one raid,
`sync` makes one extra `gh pr view --json files` call to list the PR's
changed files; any glob one of them matches is appended as
`Shared areas touched: <glob1>, <glob2>`. If that extra call fails, the
notice still posts without the shared-areas line, and the failure is
reported the same way any other `gh` failure is — as a sync failure, so the
command's exit code is non-zero. A PR whose owning party is in no raid gets
no notice, same as today. The merge is announced at most once, ever: the
notice payload carries `announces: pr:<repo>#<n>`, and `sync` skips posting
if a notice (active or not) with that `announces` value already exists —
safe across a re-sync or a `rebuild` followed by a `sync`.

Migration version clash: when the project sets `migration_paths`, every
`sync --source gh` also lists the changed files (one `gh pr view --json files`
call per open tracked PR of the project's repos), keeps those matching a
`migration_paths` glob, and takes the leading digits of each filename as its
version. When two or more distinct open PRs carry the same version, a notice
naming the version and the PRs is posted to every raid of each involved
party. Each (project, version, PR) is announced at most once, ever, through
an `announces: migration:<project>:<version>:<repo>#<n>` value, so re-syncs
do not repost. A failed files call is reported as a sync failure. Parties in
no raid get no notice.

The same sync also releases shared-area claims: when the project has
`shared_areas` and the owning party is in a raid or holds an active `area:`
claim in that project, the changed files are fetched once (shared with the
notice), and every `area:<glob>` claim of the owning party whose glob one of
them matches is released with a normal `claim.released` event. Claims held
by other parties and `task:` claims are never touched. If the files call
fails nothing is released and the failure is a sync failure. When something
was released and the owner is in a raid, the notice ends with
` Released: <glob1>, <glob2>.`

Base branch fast-forward: when the project sets `"fast_forward_base": true`,
a `sync --source gh` run that detects a merge updates the local base branch of
each merged repo once per run. Local clones are the git main checkouts (not
linked worktrees) matched by the project's `paths` globs whose `origin` URL
(https, ssh or path form) ends in a `github.repos` entry; the base branch is
read from `origin/HEAD`. Steps: `git fetch origin`; if the base is not checked
out in any worktree, `git fetch origin <base>:<base>`; if it is checked out
and that worktree is clean, `git merge --ff-only origin/<base>`. A dirty
worktree or a diverged base is left untouched and a `project:<name>` notice
`local <base> of <repo> N commits behind origin, not updated: <reason>` is
posted, at most once per origin tip. Absent or `false` → guild never mutates
a clone. `guild doctor` and `guild brief` warn when a located local base is
behind its `origin/<base>` ref regardless of the flag (they never fetch, so
the comparison uses the last fetched state).

Base drift: `guild sync --source bases` runs `git fetch origin <base>` in
each located clone of every project, regardless of `fast_forward_base`; it makes
no GitHub call and touches no tracker or SDD data, so the background job
runs it every minute. `sync --source gh`
does not fetch bases. The fetch only updates `origin/<base>`; local branches and
worktrees are never touched. A failed fetch is a sync failure
(`<repo>: base fetch failed: <error>`). `guild board` and the web header read the
result live with `git rev-list`: one line per clone,
`<repo> <base>: N behind` (`, M ahead` when above 0) or `<repo> <base>: up to
date`, followed by `(fetched Xm ago)` or `(never fetched)` from the mtime of the
clone's `FETCH_HEAD`. A clone without `origin/HEAD` shows `<repo>: no origin/HEAD (git remote set-head origin --auto)` and one whose comparison fails shows `<repo> <base>: cannot compare`, both as warnings. A `paths` entry that is not itself a clone also yields its direct child directories that are clones. Nothing is stored.

Pause a base: `guild base pause <owner/repo>` stops `guild sync --source bases` (and the
fast-forward after a merge) from fetching that repo's clones, for when you are not working on
it; `guild base resume <owner/repo>` fetches again. The repo must belong to a project; pausing
twice or resuming a base that is not paused fails. A paused base shows `<repo>: paused` on the
board, without a warning. The pause is stored (`base_pauses`) and replays in `guild rebuild`.

Per-PR drift: for each open tracked PR with a `branch` and a located clone, the
board counts `git rev-list --count origin/<branch>..origin/<base>` in that clone
(`<base>` is the PR's base branch, else the clone's) and shows a dim
`N behind <base>` line under the PR, and a pill on the web PR card
(`behind` in the board model), only when N is above 0. It is read from local refs
at read time and stored nowhere, so it is as fresh as the last local push of the
branch and the last bases fetch; a branch pushed from another machine, or missing
locally, shows nothing. It is informational: not a review reason, and it changes
no order, wait or exit code.

`guild` has no daemon, so this only fires when someone runs the sync. Someone
in the raid should keep a watcher running for the duration of the raid, e.g.
`watch -n 300 guild sync --source gh` from a terminal, or `/loop 5m guild
sync --source gh` from a session that supports it.

### `guild history`

Read-only record of what the guild has achieved. Six sections:

1. In progress: quests whose projection state is `active`, ordered by creation date (newest first, undated last), with
   party, project, epic, start, age, task counts (done, active, blocked, queued) and
   percent done. Read from the `quests`/`quest_tasks` projections plus the `quest.added`
   timestamp. Quests finished by `guild party close` leave this list.
2. Completed quests, ordered by creation date (newest first, undated last). Each shows party, project, epic progress,
   start/end and duration, tasks done, JIRA cards done, PRs merged, handoffs and
   ask metrics, read from the `achievement` snapshot frozen in the `quest.done`
   event. Quests closed before snapshots existed are derived from events
   (dates, party, tasks, PRs, handoffs) and marked `no snapshot`.
3. Closed without completing: quests flagged with `guild quest incomplete`, ordered by
   creation date (newest first, undated last), with title, party, dates, reason and how many tasks were not done at
   marking time. They do not count in totals or in finished raids.
4. Finished raids, ordered by creation date (newest first, undated last): raids with no active member, derived from
   `raid.joined`/`raid.left`/`party.closed` events and membership expiry. Each
   shows start (first join), end, parties, quests completed and
   PRs merged by member parties inside that window, and the pause count.
5. Lifecycle failures, newest first: failed, timed-out and errored `lifecycle.ran`
   events with the project, event, status, exit detail and the last non-empty
   output line. Narrowed by `--project` only, since a lifecycle run has no party.
6. Totals: quests done, PRs merged, tasks done, asks answered, median ask answer
   time, handoffs.

`--party`, `--raid` and `--project` narrow every section except lifecycle
failures; they combine.

### `guild cost`

Reports token usage per session, party, model, quest or task, read from the
Claude Code transcripts (`~/.claude/projects/*/<session>.jsonl` and
`*/<session>/subagents/agent-*.jsonl`). Each run first collects new usage, then
prints the table.

What it reads: only `message.usage`, `message.model`, the line `type`, its
`timestamp` and `message.id`. The id is used only to dedupe and the timestamp
only to bucket by UTC day and task window. Nothing else from the transcript is
stored.

Collection is incremental: a byte-offset cursor per transcript
(`transcript_cursors`) means a re-run reads only what was appended. A line
without a trailing newline is not consumed until it is complete. Lines newer
than a 10-minute grace are left for the next run, so a message still being
streamed is not counted early. A file smaller than its cursor restarts from the
beginning. Streamed chunks of one message id count once, with the highest value
of each usage field.

Each run records one `cost.sampled` local event per session, UTC day, model,
party, quest and task, holding only the increment since the last run, and only
when it is non-zero. The `cost_samples` projection sums them and `guild rebuild`
reproduces it from events; the cursors are not rebuilt.

Attribution: the session maps to a party through the latest event of that
session that carries a party. A message belongs to a task when its timestamp
falls inside a window that opens at `task.started` and closes at the next
`task.blocked` or `task.done` of the same task (open-ended if none); when
windows overlap the latest start wins. Everything else has no task, shown as `-`.
Subagent transcripts count under their parent session.

```
guild cost --since 3d --by party
party      input  cache write  cache read  output
beta       0.004        1.820      96.310   0.211
unbound    0.001        0.310       8.402   0.020
total      0.005        2.130     104.712   0.231
```

`--since` takes a duration (`30m`, `8h`, `3d`) and keeps days from that date
on. `--by` defaults to `session`; `task` shows `quest/tid`. `--project`
keeps samples of parties in that project (unbound usage has no project and is
excluded). Values are millions of tokens with three decimals, ordered by total
descending. With nothing to show it prints `no cost data`.

Limitations: usage recorded before a session is bound is `unbound` and is not
reattributed afterwards. There is no pricing: only token counts.

### `guild compact`

Every sync run appends a full snapshot to the event log even when nothing
changed, so the database grows without bound. `guild compact` shrinks it
without changing any projection.

```
guild compact [--dry-run]
```

It keeps only the two newest `epic.synced` events per project and epic and
the two newest `tracker.synced` events per project: each one is a full
snapshot that replaces the previous one, and the second newest stays as the
last known change. For each run of consecutive identical `pr.synced`
events (per PR, ignoring `synced_at`, and broken by any other `pr.*` event of
that PR) it keeps the first and the last and deletes the ones in between. So
`guild rebuild` gives the same projections and the board freshness (newest
event per project and kind) does not move. It also deletes `resources.sampled`
events and the `resource_samples` and `resource_machine` rows older than the
global `resource_retention_days` (90 when absent), and the per-session files
under `$XDG_STATE_HOME/guild` (`ctx/`, `ctx-baseline/`, `background/`) not
touched for 30 days.

Before deleting anything it copies the database with SQLite's online backup to
`$XDG_DATA_HOME/guild/guild.db.pre-compact`, overwriting the previous copy; if
the copy fails nothing is deleted. After the deletes it records one local
`db.compacted` event and runs `VACUUM`, which needs free disk of about the
database size and fails with a clear error if the database is locked (the
deletes are already committed then). `--dry-run` prints what would be deleted
and neither backs up nor changes anything. A second `compact` while one runs
prints `compact already running`. The background job runs it at `Nice=19`
(see "Background jobs"). On a large database `compact` blocks
writes to the database for about a minute, so run it when idle; readers keep
working.

Web: the "resources" section has a "Compact db" button, which posts to
`POST /api/compact` and runs the same function. Next to it, a "Collect now"
button posts to `POST /api/resources/collect` and runs `guild resources collect`.

### `guild resources`

Shows per project how much disk the repo occupies and how it grew, so a repo
filling the machine is noticed before the disk is full, even when nobody was
watching. It measures and reports; it never deletes, cleans or alerts (cleanup
belongs to the lifecycle commands), it does not measure per-container or
per-process memory, and it has no thresholds.

```
guild resources collect                 # measure now and record the samples
guild resources [--project <name>] [--since 1d]
```

`collect` is what records history; the report only reads it. The background job
runs it every 2 hours at `Nice=19` (see "Background jobs").

The web board shows the same values as coloured pills (disk green under 70%,
amber under 85%, red above; RAM red under 10% available; CPU load per core amber from
0.8, red from 1.5; growth amber, shrink or
no change green; unmeasured values grey) and a disk pill in the sidebar. The
report itself still has no thresholds.

What is measured:

| Category | Source | Attributed to |
| --- | --- | --- |
| `worktree` | `du -s -B1 -x` of each clone and `git worktree list` entry, excluding worktrees nested inside it | the project whose clone lists it |
| `docker_container` | writable layer of each container | compose working directory label |
| `docker_image` | unique size of each image | its containers, else the compose project name prefix |
| `docker_volume` | size of each volume | compose project label |
| `claude_scratch` | `/tmp/claude-<uid>/<encoded cwd>/...` | the checkout whose encoded path matches |
| `claude_transcripts` | `~/.claude/projects/<encoded cwd>/...` | the checkout whose encoded path matches |
| `docker` | marker row, only when Docker cannot be read | unattributed |

Machine totals are stored with every sample: disk used and total of `/`,
memory total and available, Docker totals (images, reclaimable images,
containers, volumes, build cache) and the size of the guild database with its
`-wal` and `-shm` files. Build cache is machine-level only.

Attribution: a checkout directory name encoded like Claude Code does
(`/home/u/app` becomes `-home-u-app`) matches the directories whose name is
that or starts with it plus `-`; when several checkouts match, across all
projects, the longest path wins. A Docker object follows the compose labels
`com.docker.compose.project` and `com.docker.compose.project.working_dir`: a
container goes to the project whose checkout or `paths` prefix contains the
working directory (longest wins, a tie goes to the first project by name). A
volume follows the working directory of its compose project, or a worktree
whose name matches the compose project. An image follows the containers that
use it when they agree, else the longest compose project name that prefixes its
repository. What cannot be attributed goes to `unattributed`. Image size is the
unique size, so layers shared between images are not counted per image and the
sum is approximate.

Flags, computed at collect time and stored with the sample:

- `merged, still on disk` and `closed, still on disk`: the latest PR of the
  worktree's branch is merged or closed. The main checkout and detached
  worktrees are never flagged.
- `orphaned`: the compose project's working directory no longer exists, or it
  has no container and no checkout whose name matches it.
- `dangling`: an image with no repository. `unused`: an unattributed image no
  container uses (dangling wins).

Reading the report: it compares the latest sample of each project with a
baseline, the newest sample at or before `--since` (default `1d`) or, if none is
that old, the oldest one, marked `(oldest available)`. With a single sample
there is no baseline and no deltas. Per category it shows the total and delta
and the 10 biggest items (`+N more` for the rest); an item absent from the
baseline is `new`. `top growers` lists the up to 5 items that grew at least
1 MiB (a new item counts with its whole size). The `machine` line shows disk
use, memory available, CPU load per core (1-minute load over the core count, with
the 15-minute load), Docker totals, the database size and the sample age.
`untracked growth` appears when the disk grew at least 1 GiB more than every
tracked delta together, which is how the next unknown cause shows up.

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

Unavailable and slow parts: nothing that cannot be measured stops a collect or
becomes a zero. An item that could not be read is `unavailable`, one whose
`du` hit the 300 s limit or arrived after the 20 minute whole-run deadline is
`skipped`, and a vanished worktree is `missing`; all store null bytes, show as
`?` and are left out of totals and deltas. Docker failures record a `docker`
marker with the reason (`not installed`, `permission denied`, `daemon
unreachable`, `timeout`, `unparseable`). The summary line, for example
`sampled 4 projects, 87 items in 94s; unavailable: docker (permission denied);
skipped: 2`, exits 0 unless there are no projects or the write fails. A
collect that finds another one running prints `collect already running` and
exits 0 (lock `$XDG_STATE_HOME/guild/resources/collect.lock`).

Cost and storage: sizes are measured one at a time with `du`, which can take
minutes on large trees, hence the background job's low priority. All measuring happens
before a single write transaction records every event, so the database is
never locked while `du` or Docker runs. Each collect adds one `resources.sampled`
local event per project plus one for unattributed items, roughly 3 KB each; at
the recommended cadence that is about 30-40 MB a year in total. `guild compact`
deletes samples older than the global `resource_retention_days`, 90 days when
absent (see "`guild compact`").

Web: the board has a collapsible "resources" section built from
`GET /api/resources[?project=<name>&since=<dur>]` (default `since=1d`), the
same model as the CLI: `machine`, `projects` and `unattributed`, each with
categories, items, growers and the baseline. An unknown project or invalid
window answers 422. It is not part of `/api/board`, and every category and flag
has a tooltip.

Privacy: collection is read-only and runs a fixed argv with no shell and a
timeout; nothing from a project config is executed. Samples hold local paths,
branch names, Docker object names and byte counts, as local events that are
never exported. Of a container only its name, size, compose project name and
working directory are read: no commands, environment or other labels.

### Lifecycle commands

A project can declare a command per PR lifecycle event in its `lifecycle`
config block (see "Project config"). Guild launches it without a model, from
the main checkout, and records the outcome. It never learns what the command
does.

```json
"lifecycle": {
  "on_pr_merged": {"command": ["scripts/cleanup-merged.sh", "--dry-run"], "timeout_minutes": 30},
  "on_pr_closed": {"command": ["scripts/cleanup-merged.sh"], "timeout_minutes": 30}
}
```

- Exit codes: an entry may add `"ok_exit_codes": [5]`, a non-empty list of
  unique integers from 1 to 255. A command that exits with a listed code is
  recorded as `ok` and posts no notice; any other non-zero exit stays
  `failed`. Use it for a script whose non-zero exit means a normal outcome,
  such as skipped work.
- When it fires: `guild sync --source gh` sees a tracked PR become `merged`
  (`on_pr_merged`) or `closed` without merging (`on_pr_closed`). PRs already
  merged or closed when tracked, seeded PRs and anything that happened before
  the PR was tracked never fire: events are never historic.
- Argv only: guild runs exactly the declared argv with no shell and no
  interpolation of PR data, and never appends flags. A dry-run flag in the
  config is the project's own choice.
- Where and how: from the main checkout of the first triggering repo (sorted),
  in its own process group, blocking, after the rest of the sync pass. When
  `timeout_minutes` elapses the whole process group is killed. A missing
  checkout is an error, never a fallback.
- Debounce and lock: triggers seen in one pass are grouped per project and
  event and run once. A lock per project and event
  (`$XDG_STATE_HOME/guild/lifecycle/<project>-<event>.lock`) stops overlapping
  runs; a run that finds it held is recorded as `skipped` (reason `locked`)
  and its triggers are lost: guild does not retry them.
- Record: a local `lifecycle.ran` event with the project, event, repo,
  triggers (`acme/app#12`, or `manual`), argv, cwd, status (`ok`, `failed`,
  `timeout`, `error`, `skipped`), exit code, duration and the last 2000
  characters of merged stdout and stderr with control sequences stripped.
  The output tail stays local: it is never exported to guild visibility.
- Failure notice: a failed, timed-out or unlaunchable command, or a missing
  checkout, posts one notice to `project:<name>` (12h) such as
  `lifecycle on_pr_merged failed for acme (exit 1): see guild history`. It
  carries no output and no argv. Sync does not count it as a failure and its
  exit code is unchanged.
- By hand: `guild lifecycle run <on_pr_merged|on_pr_closed> [--repo R]
  [--dry-run]` resolves the project from the current directory and the
  checkout from `--repo` or the single clone (several clones need `--repo`).
  `--dry-run` only prints `would run: <argv> (cwd <path>, timeout 30m)` and
  records nothing. A real run takes the same lock, records the trigger
  `manual`, prints `lifecycle on_pr_merged: ok (exit 0, 3.2s)` and exits 1 on
  failure, timeout or error.

Trust boundary: the command runs unattended with your privileges, right
after the main checkout is fast-forwarded. A merged PR that edits a
repo-relative script therefore makes the next run execute that new code. Point
`command` at an absolute path outside the repo, or at a script you review.

Output: the stored tail can contain secrets the command prints. It lives only
in the local database (never exported, never in a notice). The command runs
with stdin closed and `timeout_minutes` is capped at 1440. Output goes to a
temporary file, so a descendant that detaches from the process group cannot
hold a run (or its lock) open past the timeout. Any error while handling a
group is recorded as `lifecycle.ran` with status `error` and does not stop
the other groups or the sync.

Out of scope: `on_main_red` (sync cannot tell a first red observation from a
new failure), `on_worktree_created`, a resource officer (see the `officers`
epic), detached runs, retries, re-running lock-skipped triggers, and moving
the runner under a scheduler.

### Waiting for a change

`guild ask wait <id>` and `guild pr wait <owner/repo>#<n>` block until
something changes, so a session can start them in the background and wake up
on the change. They poll every 15 seconds and read only guild's stored state:
no sync, no GitHub call, no write. A PR only changes in that state when a sync
runs, so `pr wait` starts the due background syncs itself while it waits
(see "Background jobs"). `--timeout` (default `2h`, such
as `30m` or `4h`) ends the wait with exit 3.

`ask wait` exits 0 when the ask is answered or dismissed and 1 on an unknown
id. It never prints the answer: read it with `guild asks <id>`.

`pr wait` exits 0 when the PR is merged or closed (also when it already is),
when a comment or review by someone other than the PR author appears (the
count is compared with the one at the start of the wait, whichever head it
came before), or when its checks go from pending to finished. The output is one
fixed line with the ref and counts; it never prints comment text. Comments
from the same account as the PR author do not wake it. Notice-only comments
configured with `human_ready.notice_comments` do not either. Exit 1 is an
untracked or malformed ref, or a PR that has not been synced since the comment
count existed (run `guild sync --source gh` first). The count only moves
with a sync: a comment deleted and another added between two syncs leaves it
unchanged and does not wake.

### Background jobs

`guild` has no daemon and installs no systemd timers. Seven jobs keep the stored
state fresh, and each starts, detached, when it is due and one of these runs:
a session hook (`session-start`, `prompt-submit`, `stop`), a `pr wait` that
sees no sync for 30 minutes, or `guild web`, which checks every minute while it
runs, with or without a browser open. Leave `guild web` running (tmux, a login
autostart) for a schedule like the old timers. An idle machine, with no session
and no `guild web`, runs nothing.

| job | command | every |
|---|---|---|
| `sync-gh` | `guild sync --source gh` | 10m |
| `sync-sdd` | `guild sync --source sdd --all-projects` | 10m |
| `sync-tracker` | `guild sync --source tracker --all-projects` | 10m |
| `sync-bases` | `guild sync --source bases` | 1m |
| `resources-collect` | `guild resources collect` | 2h |
| `solo-tick` | `guild solo tick` | 10m |
| `compact` | `guild compact` | 1d |

`resources-collect`, `solo-tick` and `compact` run at `Nice=19`. The last start of each job
is a stamp file in `$XDG_STATE_HOME/guild/due/`; a job is due when its stamp is
missing or older than its interval, and the stamp is touched before the start,
so two hooks never start the same job twice. The `--all-projects` syncs visit
every project config that has an `sdd` (or `tracker`) block and skip the rest
without a failure. A project whose sync fails (unreadable SDD root, `acli`
missing or not logged in) is reported as `<project>: <reason>` and the run exits
non-zero; the previous tracker snapshot is kept.

### `guild merge-queue`

`guild merge-queue [--raid <name> | --party <name>]` prints every open tracked
PR in priority order, blocked ones included and kept in place, with the next
action for each: `merge`, `promote: gh pr ready → <party>`, `wait: <reasons>`
or `fix: <reasons> → <party>`. It is read-only: no
network call, no event. **Guild never merges**: the output is advice for a
human, who merges by hand and re-runs the command after each merge (the
last line of the output says so).

`guild merge-queue --head` prints only the first entry whose action is `merge` or `review: human, then merge`
(PRs blocked by something outside development are skipped) as
`<ref> <party> <task>`, or `no PR ready to merge`; it takes the same scope flags.

**Review list.** `guild review-md [--raid <name> | --party <name>]` prints the
PRs ready for the person as one markdown document, in the order of `guild
merge-queue`, with the same scope flags and rules. A PR is listed when it is
`ready` (not draft), its human state is `ready` or `ready (CI pending)`, it is
not blocked by something outside development, its action is `merge` or
`review: human, then merge`, and its repo has no red main (a main blocked by
billing does not exclude it). Each PR is `- [ ] <owner/repo>#<n> <title> — <url>`
followed by indented lines: `review: human first` when the action is the human
review one, `checks: <n> passing` (also failing and pending counts), and one
`note: <x>` per note of `guild pr ready-check`. With nothing to list it prints
`Nothing is ready for you.`; it exits 0 either way. The output carries no
tool-internal names, so it can be pasted outside the CLI.

**Ready for you on the board.** `guild board` prints a `READY FOR YOU` section
right after `NEEDS YOU`, and `guild web` shows a "ready for you" section under
the open asks (model key `ready_for_you`). Both list the PRs picked by the same
rule as `guild review-md`, in the board's queue order (raid queues first, then
one per party outside raids), each PR once: `<ref> <title> · <party>`, `· review
first` when the action is the human review one, and one indented `note:` line
per note. `guild board --party` and the web party view keep the PRs of that
party; `guild board --raid` and the web raid view keep every PR whose queue
is in that raid, so a PR shows under each raid whose queue contains it.
`guild review-md --party X` recomputes the queue over that party alone, while
`guild board --party X` filters the board's list, so cross-party pins can make
them differ; the board matches the merge queue cards. With none it prints
`READY FOR YOU · nothing` (web: `nothing is ready for you`). Read-only.

**Scope.** `--raid` takes the open tracked PRs of the raid's active members,
`--party` those of one party; the two flags are mutually exclusive. Without a
flag, a bound session uses its raid when its party is in exactly one, errors
listing them when it is in several, and uses its own party when it is in
none; a human terminal (or an unbound session) must pass a flag.

**Ready check.** `guild pr ready-check <owner/repo>#<n>` first refreshes that
one PR from GitHub (the same refresh as `guild sync --source gh`, merge side
effects included); when `gh` fails it adds `- note: state as of last sync` and
keeps the stored state. It then computes the queue
over every open tracked PR (cross-party stacks, pins and task dependencies
count) and prints `<ref> <human state>` (`ready`, `ready (CI pending)`,
`waiting` or `blocked`), then one `- <blocker>` line per blocker, one
`- <missing>` line per missing item, `- wait: <x>` per wait, `- gate: ...` per
gate (draft with the `gh pr ready <n>` hint, needs human review, `N review
comments since last read`, main red) and
`- note: <x>` per note. A PR is human-ready when it is not draft, has no
unresolved thread, no comment or review by another author after the head
commit (unknown counts as none), a valid review trace when the project
configures a validator and green CI on the head. `- review trace invalid:
<reason>` makes it `blocked` and `- review trace not validated: <reason>` makes
it `waiting`. Without any check on
the head it is `ready (CI pending)` when the project's CI label is absent from
the PR or main is blocked by billing, otherwise `waiting` with `- no checks on
head`. Unread comments are the PR's comments and reviews that no `guild next`
or `guild pr ack <owner/repo>#<n>` has marked as read; read them, then ack. The
web queue detail shows the same gate and a `Mark N comments read` button (it
never calls `gh`). It exits 0 only when the action is `merge`, the state is `ready` or
`ready (CI pending)` and there is no gate, else 1. The merge queue order does
not include human-ready: it only decides the sequence, and `guild
merge-queue` with `--head` still order and name PRs by the queue state and
action, while the human-ready state is shown by `ready-check` and the web pill.
A PR behind a PR that is not human-ready is `waiting` (`- waits on <ref>`).

**Lifecycle from GitHub.** Readiness is owned by `guild sync --source gh`, not
by sessions. An open PR that is Ready for review on GitHub becomes `ready`
whatever its guild lifecycle was; an open draft PR keeps `converging` and
otherwise (including a stale `ready`) becomes `draft`.
Merged and closed PRs become `merged` and `closed`. Agents mark a PR ready
with `gh pr ready <n>`; `guild pr set --lifecycle` remains for the
`converging` nuance. `pr set --lifecycle ready` on a PR that
is still draft on GitHub prints a hint, and the next sync reverts it.

**Relink and untrack.** `guild pr set <ref> --task <quest>/<tid>` and/or `--card <KEY>` change the task or card a tracked PR is linked to (an adventurer's PR takes `--card` only); `guild pr untrack <ref>` drops the PR (event `pr.untracked`). Use them when a merged PR only refined a spec and its card should not be reported as not done. Only the owning party or adventurer may run them; the web board offers Relink and Untrack on each PR row, as the human.

**Human flags.** Two independent booleans set with `guild pr set` and never
touched by sync: `--needs-ask-answer` (the PR is stopped until the human
answers an ask; blocks the PR in the merge queue; also derived, see below) and
`--needs-human-pr-review` (the human should review the PR before it is
merged; does not block). Each has a `--no-...` counterpart to clear it; an
absent option leaves the flag unchanged. `pr set` needs at least one option.
A PR counts as needing an answer while the
manual flag is set or an open ask refs it (`pr:<owner/repo>#<n>`), computed when
read, so answering or dismissing the ask unblocks the PR with no `pr set`. The
merge queue, `pr ready-check`, the board and the web PR pill then show
`needs-ask-answer (ask #N)`; `--no-needs-ask-answer` clears only the manual
flag, an open ask keeps blocking.
A PR that had the old `needs-human` lifecycle becomes `draft` with
`needs-ask-answer` set, both in the live database and when events replay in
`guild rebuild`.

**Manual block.** `guild pr set --blocked-external "<reason>"` (the flag keeps its name) marks a PR
that waits on something outside development (a decision, a meeting); sync
never clears it, `--no-blocked-external` does. `guild web` shows the PR with a `blocked: manual` pill carrying the reason (also on its merge-queue entry), and its Block manually (asks for a reason) and Unblock buttons, on the PR card and on its merge-queue entry, do the same from the browser, recording the same `pr.set` event with no party. In the merge queue the PR is
blocked with the reason `manual block: <reason>`, keeps its place, and its action
is `manual block: <reason>`; PRs queued after it (pins, task dependencies,
stacks) are blocked too, with the action `waits on manually blocked <ref>: <reason>`. None of them is the head of the
queue, the `next action` target or a `guild next` item, `pr ready-check`
exits 1 for them. They are excluded from `max_open_prs_per_party`, `max_open_prs` and
`max_open_prs_per_file`.

**Branch.** The full branch name of each PR is shown wherever the PR is shown: under the PR in `guild board`, at the end of its `guild merge-queue` line, and next to the PR in the web board. It comes from `pr track` and `guild sync`; a PR with no known branch shows nothing.

**Urgency marks.** Two more independent booleans, never touched by sync:
`--fixes-main` (the PR repairs a broken main branch) and `--fixes-flaky` (the
PR fixes flaky tests). Both can be set at `pr track` and flipped with
`--fixes-main`/`--no-fixes-main` and `--fixes-flaky`/`--no-fixes-flaky` on
`pr set`. Neither blocks the PR: they move it to the front of the merge queue
and of `guild next`, because a broken main or a lying test suite blocks every
party. They are a claim about the PR, independent of `guild main red`: the
mark is honoured whether or not any source says main is red, and merging the
PR never clears the red mark.

**State.** Only merge blockers decide the state, in this precedence:

- `blocked`: a check is failing, `mergeable` is `CONFLICTING`, the review
  decision is `CHANGES_REQUESTED`, review threads are unresolved, the merge state
  is `BEHIND`, a task its own
  task depends on (SDD `Depends on`, through the quest's epic) is not done by
  the same resolver `guild next` uses, it needs an ask answer (manual flag or an
  open ask), or a PR
  that must come before it (by task dependency or pin, transitively) is
  blocked (`waits on <ref>`). Every reason that applies is listed: `needs ask answer`,
  `checks failing (N)`, `merge conflict`, `changes requested`,
  `N unresolved threads`, `behind base`, `waits on task Txx`, `waits on <ref>`.
  Missing review data counts as no signal.
- `waiting`: not blocked, but checks are still running (`checks pending (N)`)
  or a PR that must come before it is itself waiting or ready but still draft
  (`waits on <ref>`).
- `ready`: neither of the above.

Check counts come from the `statusCheckRollup` of `gh pr view` (check runs
and legacy commit statuses): a check run that has not completed and a status
that is `PENDING` or `EXPECTED` count as pending, `FAILURE` and `ERROR`
statuses count as failing, skipped and neutral runs are not counted. The
pending count is stored in `prs.checks_pending` (column migration, rebuilt
from the `pr.synced` event; events from before it replay as unknown).
Failing checks beat pending ones: a PR with both is blocked. Merged and
closed PRs never appear.

**Labels.** The type (`[feat]`), then `draft` and `converging` (the lifecycle
from GitHub), then `fixes-main` and `fixes-flaky` (the urgency marks), then
`needs-ask-answer` and `needs-human-pr-review` (the human flags), are labels
shown in brackets after the task, `[draft]`; only `needs-ask-answer` blocks. A draft that
is otherwise `ready` is worth promoting, and one that is blocked or waiting
is not.

**Action.**

| State | Label | Action |
|---|---|---|
| blocked | any | `fix: <reasons> → <party>` |
| waiting | any | `wait: <reasons>` |
| ready | `draft` / `converging` | `promote: gh pr ready → <party>` |
| ready | `needs-human-pr-review` | `review: human, then merge` |
| ready | none | `merge` |

Waiting and ready actions are followed by the order notes in parentheses
(`ready, checks ✓N`, `before ...`, `after ...`, `pinned ...`).

**Order.** All open PRs are put in a topological order over hard
constraints, and ties between PRs that are free to go first are broken by
value:

1. SDD task dependencies between the PRs' tasks.
2. Pins: explicit `X before Y` agreements (below). A pin that involves a
   merged or closed PR is ignored, so stale pins drop out by themselves. A
   pin whose first PR is blocked keeps that PR in place and the second one
   waits on it.
3. Among the PRs that are free, one marked `fixes-main` or `fixes-flaky` goes
   first (both marks weigh the same), with the reason in its order notes
   (`fixes a broken main`). A mark reorders only the PRs that are free to go:
   it never jumps a task dependency or a pin, so a marked PR in the middle of a
   chain still waits for the PR it depends on.
4. Among the rest, the one that unblocks the most goes first
   (`unblocks N`: the distinct open PRs that depend on it, directly or
   transitively, plus the open PRs of the same repo that touch the same
   project `shared_areas` glob), then the lower PR number, then the repo.

A blocked PR is not moved to the bottom: if the top PR is blocked, fixing it
is the first thing to do. `▶ next action:` marks the first blocked PR that
sits above at least one PR whose action is `merge`.

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

If pins and task dependencies contradict each other, the PRs involved are
listed at the end as blocked with the cycle named (`fix: ordering cycle ...`)
rather than ordered arbitrarily.

**Main red.** A red base branch comes first, as row `0.`, for every repo
among the shown PRs. Two sources feed it: `guild sync --source gh` reads the
check runs of the base branch (`gh api repos/<repo>/commits/<branch>/check-runs`)
for each project repo that has a local clone with a known base branch, and
it is red when any run failed, was cancelled, timed out or needs action. When
no check run of the head commit fails, it also reads the last 30 workflow runs
of the base branch (`gh run list --branch <branch>`) and is red when the latest
decided run of a workflow failed, timed out or failed to start (reason
`workflow <name> failed @ <sha7> (run <id>)`): this catches a repo whose CI on
the base runs on a schedule or by hand, so the head commit has no CI checks.
Runs still in progress, cancelled or skipped fall back to that workflow's
previous run, a later green run clears it, and Dependabot update runs (event
`dynamic`) never count
(event `main.status_synced`, one event per change, source `gh`); and
`guild main red <repo> --reason "<text>"` / `guild main green <repo>` mark it
by hand (event `main.marked`, source `manual`). A repo is red when any source
says so; `green` clears only the manual mark, the `gh` mark clears on the next
sync that sees the base branch green. Projection `main_status`, rebuilt like
everything else.

**Main blocked by billing.** When GitHub Actions cannot run because the
account's billing failed, every job of main fails without starting. The sync
fetches the annotations of each failing run (`gh api
repos/<repo>/check-runs/<id>/annotations`, only for runs that have any) and,
when every failing run carries the message `recent account payments have
failed` (or has no annotations and finished within 5 seconds of starting, which
is how a job refused for billing looks), stores the mark with `external` = `billing` (`main_status.external`,
carried by the `main.status_synced` payload; events without it replay as an
ordinary red). The queue then shows `0. MAIN BLOCKED (billing) <repo> →
re-run main once billing is fixed` instead of `MAIN RED`, `guild board` and the
web card show the same, `guild pr ready-check` lists the note `main blocked:
billing` and does not fail on it, and the push hook does not refuse: it warns `main of
<repo> is blocked by billing: CI will not run`. A single failing run with
another cause keeps main red. Re-run main's last run once billing is fixed;
the next sync clears the mark.

The same test runs per open PR with failing checks, over the check runs of its
head commit (`prs.checks_billing`: 1 billing, 0 a real failure, empty when
nothing is failing; it never moves the PR's last activity). Such a PR gets the
label `checks blocked by billing (n)` and is no longer a `checks failing` fix
reason in the queue, a `guild pr ready-check` blocker, a `checks-failing` party
wait nor a `failing checks` line of `guild next`, and a draft with only such
failures counts as a green draft: it shows as `ready
(CI pending)` with the note. If the extra call
fails, the PR counts as a real failure and the sync reports it.

**Data and freshness.** The order is computed from stored data, so it is only
as fresh as the last `guild sync --source gh` (the header says `synced N min
ago`, the latest sync among the PRs shown). For every open PR whose party is
an active raid member or holds an active `area:` claim, in a project that
sets `shared_areas`, that sync makes one `gh pr view --json
files,additions,deletions,createdAt` call and stores the matched globs
(`pr_shared_areas`), the diff size and the creation time (`prs.additions`,
`prs.deletions`, `prs.created_at`, added by the usual column migration, all
rebuilt from the `pr.synced` event). PRs of parties outside raids with no
claims cost no extra call, and their overlaps are unknown to the queue. A
failed call is a sync failure (non-zero exit) and keeps the previous rows. A
raid member should keep the sync running (see "Merge notices").

**Stacked PRs.** A PR whose base branch is the branch of another open PR of
the same repo merges after it; the queue shows `after X (stacked on it)` on the stacked PR and
`before Y (it is stacked on this)` on its base, and a pin
cannot invert the stack (it is rejected as a cycle).

**Pins.** `guild merge-queue pin <repo>#<a> --before <repo>#<b>` records that
`a` merges before `b` (event `merge_queue.pinned`, with the author party or
`human`; projection `merge_queue_pins`, rebuild-safe); `unpin` removes it
(`merge_queue.unpinned`). Both PRs must be tracked and open to pin. Who may
pin: when both PRs belong to members of the same raid, any active
member of that raid or the human (also when one party owns both); otherwise only the party
that owns both PRs, or the human. The human is a session-less terminal; a
bound session acts as its party and an unbound session is refused. A pin that
would close a cycle with existing pins, stacks or task dependencies is rejected
naming the cycle (`pin would create a cycle: a -> b -> a`), a duplicate pin
and an `unpin` of a missing pin are errors. `unpin` still works after a PR
merges.

`guild board --raid <name>` starts with `MAIN RED: <repo> — <reason> (<source>)`
for each red main and `next to merge: <ref>` (the first PR of the
queue whose action is `merge`), and each party block of `guild board` shows the same lines for that
party's own queue, when they exist. `guild web` shows the same queues, see below.

`guild board` also prints one `project <name>` block per project of the parties
shown, before the party blocks: `open PRs: N/cap` and the cap `wait:` line
when `max_open_prs` is set, one `hot file:` line per file touched by at least
`max_open_prs_per_file` open PRs (same counting as the pre-push warning),
one `finding class:` line per class (marked `(at threshold)` at or above
`finding_guard_threshold`) and `sdd synced Xm ago, tracker synced Ym ago`
(`never` before the first successful sync). Each party block shows
`open PRs: N/cap` and its `wait:` line when `max_open_prs_per_party` is set.
`guild finding list` prints the finding classes of the project with their PR
counts.

Each party block of `guild board` prints a `waits on:` line after `status:`
when the party's open work waits on something: `checks pending (N)`,
`checks failing (N)`, `merge conflict`, `behind base`, `changes requested`,
`N unresolved threads`, `human review`, `merge` (a ready PR to merge by hand),
`green draft: mark ready`, the fix request tag, `ask #N open`, `ask #N answered`
and `notice #N unread` (not yet read by the leader session), and `resets HH:MM`
or `reset: resume by hand` when the live leader hit a usage limit. Only open
PRs count and closed parties show nothing. The model key is `waits`
(`kind`, `subject`, `label` per wait).

### `guild drift`

`guild drift [--epic <slug> | --all]` reports, for the project resolved from
cwd, every disagreement between guild, SDD and the tracker that the last
`guild sync --source gh|sdd|tracker` observed. Read-only: it never fires an
event and never calls `gh` or `acli` — it only reads the projections a prior
sync filled.

Without flags, the report is scoped to work in progress: every epic-scoped
rule (`tracker and SDD disagree`, `SDD task without card`, `card not under
its epic`, `epic done with open work`, `quest task not in SDD`, `task done,
SDD not done`, `task started, card not started`) runs only on epics referenced by an
`active` quest of the project, and every PR rule (`merged PR, task not
done`, `PR open, card not started`, `PR merged, card not done`, `PR closed unmerged`) runs only on PRs
tracked by a party that is `active` or `awaiting-leader`. `party has no
running leader` and `session leads several parties` are unaffected by scope, always project-wide;
`adventurer task not in SDD` is project-wide too, and only `--epic` narrows it. `--all` drops
this default and reports the whole project (the audit mode). `--epic <slug>`
restricts every epic-scoped rule to that epic, regardless of quest state;
`--epic` and `--all` are mutually exclusive. The first line always states
the resolved scope, e.g. `scope: 2 epics in active quests (use --all for the
whole project)`, `scope: no epics in active quests`, `scope: whole project`
or `scope: epic <slug>`. Exit code is always 0 (it is a report, not a
check); output then groups findings by rule, in this order, each finding
naming the refs and what each source says:

| Rule | Finding when |
|---|---|
| `merged PR, task not done` | a tracked PR has lifecycle `merged` and its linked quest task state is not `done` |
| `tracker and SDD disagree` | a task has a synced card and `sdd_status`, and card done (`status_category == done`) disagrees with `sdd_status == done` |
| `SDD task without card` | the epic has a `jira_key` but the task has none (only for keyed epics) |
| `card not under its epic` | the epic has a `jira_key` and the task's synced card has `parent_key IS NULL` |
| `PR open, card not started` | a tracked PR is not merged/closed and its linked card (the task's SDD card, or the `--card` key of `pr track`) has `status_category == new`; names the card and says to move it to In Progress |
| `PR merged, card not done` | a tracked PR has lifecycle `merged` and its linked card (task's SDD card or `--card` key) has `status_category != done`; one finding per card, listing its merged PRs, says to move it to Done |
| `task started, card not started` | a quest task is `active` in guild and its SDD card has `status_category == new`; says to move the card to In Progress |
| `PR closed unmerged` | a tracked PR has lifecycle `closed` |
| `party has no running leader` | an `active` party's `leader_session_id` is not the id of any session file under the Claude sessions dir (`awaiting-leader` parties are not findings) |
| `session leads several parties` | one session id leads more than one `active` party of the project (a double binding from before `party start` and `party resume` refused a second party); `guild doctor` shows the same finding as a `warn` |
| `epic done with open work` | the epic's `sdd_status == done` but it still has a non-done quest task, or an open tracked PR linked to it |
| `quest task not in SDD` | a task of an epic quest has no synced task with that tid in the epic's `tasks.md` (typically added with `guild task add` and never written to the SDD) |
| `task done, SDD not done` | a task of an epic quest is `done` in guild while the epic's synced `sdd_status` for that tid is not `done` |
| `discarded task in SDD` | a task of an epic quest was discarded in guild while the epic's `tasks.md` still lists that tid; remove it there or run `guild task restore` |
| `adventurer task not in SDD` | an adventurer held `<epic>/<tid>` of a synced epic, one of its tracked PRs is `merged`, and the epic has no synced task with that tid (a mistyped tid, or a task the PR never added to `tasks.md`); a sync of the SDD after the merge clears a correct one |

The last line is `N findings` or `no drift`. `guild drift` never writes to
SDD or the tracker: fixing drift stays with humans and the normal skills.

### Ideas

A backlog for loose ideas that would otherwise live on post-its. An idea has a
title, a description, a creation date and, optionally, a requester (free text),
a deadline (`YYYY-MM-DD`) and a registered project. The human and any session
can add, edit and delete ideas; they are local and never broadcast. `guild
ideas` lists them by deadline ascending with the ones without deadline last
(ties by creation), and marks `overdue` the ones whose deadline is before
today. When a party or an adventurer starts work from an idea it runs `guild idea link <id>`
(an adventurer session is detected on its own);
`guild idea unlink <id>` drops the link, and is refused once the party or adventurer tracks a PR. A session links only itself;
from the human terminal `--party <name>` or `--adventurer <id>` is required. The party must exist and
not be closed, the adventurer must be active, and linking twice is refused. `guild ideas` and `guild ideas
<id>` show `worked by: <party>, adventurer <id>, ...` (closed parties marked `(closed)`, adventurers that
are not active marked with their state), each party block in `guild board` lists its `ideas`, and so does each
adventurer. The `adventurer done` final report lists the linked ideas. Promoting an adventurer moves its links to
the new party; a done or dismissed adventurer keeps its links. The web ideas section links and unlinks adventurers too. Once the work is done the
session runs `guild idea delete <id>`, which also removes the links: a deleted
idea stays in the event log and `guild rebuild` deletes it again. Idea ids are local; do not copy
them into PRs, commits or cards. Title, description and requester go through
the same email, secret and project-pattern checks as other free text.

The board has an `ideas` section (the same list, in the same order, with an
`overdue` flag per idea) with a form to add one and `Edit` / `Delete` on each
card. `POST /api/ideas/create` (body `{"title", "description"}` plus optional
`requester`, `deadline`, `project`, each a string or `null`),
`POST /api/ideas/<id>/edit` (body with the fields to change; `null` clears
requester, deadline or project) and `POST /api/ideas/<id>/delete` (body `{}`)
run the same functions as the CLI; invalid input answers `422` with the
message, a wrong type `400`. The project select lists every registered
project, and the deadline is typed as `YYYY-MM-DD`. Each idea shows its linked
parties with `Unlink`, and a select of active parties with `Link`; the party
card lists its ideas. `POST /api/ideas/<id>/link` and `/unlink` (body
`{"party"}`) run the same functions as the CLI. The description is a
multi-line text box and its line breaks are kept when the idea is shown. Each
idea shows its creation date and, after an edit, its update date; an idea with
no linked party shows `not linked yet` (in the web and in `guild ideas`).

#### Moving ideas to another guild

`guild idea export` writes ideas to a new `.md` file (a heading plus one fenced
JSON block) and hides them as exported; it never deletes them. The requester
and the links are not written, because the requester may name a real person.
With ids it refuses an idea that is already exported or linked to an open party or an
active adventurer; with `--project` it takes every idea of that project and
lists the linked ones it skipped. Each idea gets a uuid that stays the same on a
later export. The file is at most 256 KiB, so `guild realm send` can carry it;
a plain copy works too. `guild idea import <file> --receipt <receipt.md>` reads
the file in one transaction (all or nothing), gives each idea a new local id,
skips the uuids it already holds, flags text that looks like an instruction and
writes a receipt with the uuids this guild now holds. Carry the receipt back and
run `guild idea confirm-export <receipt.md>`: it deletes the exported ideas the
receipt lists and reports the uuids it ignored. Check the sender that `guild
realm fetch` prints first; there is no undo after the confirmation.
`guild idea unexport <id>` brings an idea back, and warns that both guilds hold
it if the other side already imported it. Exported ideas leave `guild ideas`
and the board count; `guild ideas --exported` lists them and `idea link` refuses
them. Agents never run these four commands.

The web ideas section has an `Export` button on each idea and an export project
action, both next to a destination field: the file is saved in `idea-exports/`
under the guild data directory and its path is shown. A paste form imports an
export file (the receipt is saved there too, path shown), another confirms a
pasted receipt after a prompt, and a collapsed `exported` list offers `Unexport`
and `Delete`. The POST routes are `/api/ideas/export`, `/api/ideas/export-project`,
`/api/ideas/import`, `/api/ideas/confirm-export` and `/api/ideas/<id>/unexport`.

### Adventurers

An adventurer is one session doing one job on one project: `guild adventurer
start "<job>" --reason "<why>"` registers the session (the project comes from the cwd and must
be registered), and `--task <epic>/<tid>` ties it to one synced SDD task. A
session is a party leader, an adventurer or unbound, never two: `adventurer
start` refuses a session that leads a party or is already an adventurer, and
`party start` / `party resume` refuse an active adventurer.

The session chooses the role itself when its work will change a repo: one PR
job is an adventurer, several PRs or quests a party. `--reason` is required on
`adventurer start` and `party start` (same email, secret and project-pattern
checks as `--pending`), is stored on the event and shown on the board, in
`guild adventurers <id>` and in the web with the start time. Neither start
raises a permission prompt. When the work outgrows one job,
`guild adventurer promote <party> --reason "<why>" --goal "..." --done-when "..."` makes the same session the
leader of a new party: the adventurer ends as `promoted`, its PRs move to the
party and the party records the adventurer it came from. The adventurer's task
is not moved: the leader adds it to a quest with `guild quest add ... --tasks`.
This is the only way a session changes identity.

`--task` refuses an unknown task, a task in an active quest, a task under a
live `task:<epic>/<tid>` claim and a task another active adventurer holds.
The adventurer does not take a claim: its row holds the task, and `quest add`,
`task add`, `guild claim task:...` and `guild claim check task:...` treat it as
taken (`held by adventurer <id>`) until the adventurer is done.

`guild adventurer done --pending "<text>"` ends it. `--pending` is required;
`none` is the explicit empty report. The text goes through the same email,
secret and project-pattern checks as `handoff --learned`. `guild adventurers`
lists the active adventurers, newest first, and the ten most recent finished ones with job,
task, project, state and pending report; `guild adventurers <id>` shows one.
`adventurer done` also prints a final report block: job, task, the PRs the
adventurer tracked (`<repo>#<n> | what | state`, refreshed from GitHub first),
what it generated (its asks, the ideas it created, the open quests it added and
its notices still in force, in the same lines as the party report), a
`warning: left open: <n> asks, <n> PRs` line when an ask is still open or a PR
is not merged or closed (it warns, it does not refuse), and the pending text.

An adventurer can track its PRs (`guild pr track ... --task` equal to its own
`<epic>/<tid>`, `--card <KEY>` optional; a health-job adventurer passes no `--task`; the PR records the adventurer and an empty
party), post notices, add ideas and open asks (labelled `adventurer <id>`), and
the Stop hook records `session.stopped` for it like for a leader. Any command
that needs a party (quests, tasks, handoff, claims, `next`) refuses with
`adventurers do one job; quests and tasks belong to parties`. An adventurer's
task is done when the SDD says so. Adventurer ids, jobs and pending reports are
local: do not copy them into PRs, commits or cards.

`guild board` and the web board list adventurers, newest first, in their own section (`guild
board` hides it under `--party` and `--raid`): id, job, project, task, live or
stopped, pending report once done, and their PRs. A done adventurer stays
listed until `guild adventurer dismiss <id>` (the web Dismiss button calls the
same function; dismiss refuses an adventurer that is neither done nor active with a session gone). An active
adventurer whose session is gone carries the flag `stopped without report`.
The same flag marks an active party whose leader session is gone without a
`guild handoff` (the party is not `awaiting-leader`), in the CLI board and as a
pill on the web party card.

### Health jobs

`health_jobs` in the project config (see "Project config") names recurring
jobs. A job is `due` when no adventurer on it has reported (`done`, dismissed
or not) or the latest report is older than `every`; it is `running` while an
adventurer on it is active, and `ok` otherwise. This is computed on read from
the adventurers table: nothing runs on a timer and nothing launches by itself.

`guild board` lists due and running jobs per project in a `HEALTH JOBS` section
(hidden under `--party` and `--raid`) and the web shows the same in `health
jobs`; a due job carries the command to run, `guild adventurer launch <name>`,
as text to copy. The web has no launch button.

`guild adventurer launch <name>` is for the human terminal and refuses inside a
Claude Code session. Run from a checkout of the project, it opens a tmux window
named `health-<name>` in the first entry of the project's `paths` (the part
before the first glob character) and runs `claude` there with the job's
`command` as the first prompt, quoted for the shell the same way `guild revive`
quotes its commands, and with `GUILD_ADVENTURER_JOB=<name>` in that process's
environment. It refuses when tmux is missing or the window already exists.
Guild records the window id it created (`health_window.launched`, table
`health_windows`). After `guild adventurer done`, the `Stop` hook of that session
closes its pane when the pane's window is a recorded one and is in the `guild`
tmux session. A hand-started `claude`, a session in another window or any failed
check is left open. This runs inside the session, so the web has no action for it.

The `SessionStart` hook reads `GUILD_ADVENTURER_JOB`: in a new (`startup`)
session that is not a party leader or an adventurer yet, it starts the
adventurer for that job, the same function as `guild adventurer start --job
<name>`. When it cannot, the hook output says why (`GUILD_ADVENTURER_JOB=<name>
not applied: ...`). `start --job` takes the job name as the adventurer's job
text and refuses a job text, `--task` or a name missing from `health_jobs`.

### Solo players

`solo_players` in the project config (see "Project config") declares the
per-repo players. The identity of a solo player is `(repo, job)`. A job is
either built in, with its own prompt, class and trigger, or defined in the
config (see "Custom solo players"). The built-in jobs:

| job | class | what its session does |
|---|---|---|
| `red-main` | cleric | fixes a red main with TDD, opens a PR tracked with `--fixes-main`, never merges |
| `dependabot` | artificer | makes open Dependabot PRs mergeable (stale, identity, scope and supply-chain gates, direct fixes on the PR branch; closes a stale single-dependency PR with `@dependabot close` and drops stale dependencies from a multi-dependency PR) and fixes a failing Dependabot update run through a normal PR; never merges |

Each prompt has two parts. The rules always apply: the goal, never merge,
how to track the PR, `guild solo say` and `guild adventurer done`. The steps are
built in, unless the local clone of the player's repo has a skill named after
the job, `.claude/skills/<job>/SKILL.md`: then the session starts with
`/<job> <owner/repo>` and follows that skill for the steps, with the rules
still on top (they win on merging, tracking and messages; the skill wins on the
repo's own steps, such as how a PR becomes ready). A repo keeps its own flow
that way, and the skill stays usable without guild. `guild solo launch` and the
tick open the window in that clone; without a local clone, in the project's
first path with the built-in steps.

`name` is only a label for the board, and `class` on a built-in entry replaces
its class. Each solo player is also a health job
named `<job>-<owner>-<repo>` (the repo with `/` turned into `-`, for example
`red-main-acme-app`), so two repos with the same name under different owners
do not collide. That job has `every` `1h` and the built-in prompt; `guild
adventurer start --job <that name>` and the `GUILD_ADVENTURER_JOB` binding of
the `SessionStart` hook accept it. The `HEALTH JOBS` section lists only the jobs
written in `health_jobs`.

#### Custom solo players

An entry with a `job` that is not built in defines its own player. Every key is
required, nothing is defaulted, and `repo` is the home repo: the repo whose
clone is the working directory of the session. Put the repo a command targets
inside the command.

```json
{"repo": "acme/app", "job": "sec-audit", "name": "warden", "class": "red",
 "command": "/security-audit acme/api quick", "trigger": "every 7d"}
```

- `job`: a slug like other names, not `red-main` or `dependabot`.
- `command`: the prompt the session starts with, a non-empty string that does
  not start with `-`. Guild appends the same rules every built-in prompt
  carries: never merge, track PRs with `guild pr track` without `--task`
  (plus `--fixes-main` when the trigger is `main-red`), `guild solo say` only
  for important things, one short message before `guild adventurer done`.
- `class` and `name`: free labels shown on the board.
- `trigger`: when the player is due. `main-red` and `dependabot` behave like
  the built-in jobs of that name (including the `fixing` hold and the
  `to merge` list); `every <duration>` (for example `every 7d`, at least `1h`)
  is due when it has no report and no launch yet, or the last report or launch
  is older than the interval, and never backs off.
- `retry_after`: optional, how long a `main-red` or `dependabot` player waits
  before retrying the same trigger (for example `2h`, at least `1h`). Refused
  on an `every` trigger.

Built-in entries accept `repo`, `job`, `name`, `class` and `retry_after`;
`command` and `trigger` are refused there. The board and `guild solo list` show
the schedule of each player (`on main-red`, `on every 7d`).

Triggers come from facts the sync stores:

- `red-main`: a `main_status` row of the repo is red and not blocked by billing,
  whichever source set it (`guild sync --source gh` or `guild main red`).
- `dependabot`: `guild sync --source gh` found an open Dependabot PR that is
  not mergeable (failing checks, conflicts, behind or dirty) or a failing latest
  Dependabot update run (runs with event `dynamic`, the latest completed run
  per ecosystem). It records `dependabot.synced` only when the counts change.

`guild sync --source gh` also announces each open Dependabot PR that is ready
(mergeable, merge state clean, at least one check and all of them SUCCESS,
NEUTRAL or SKIPPED) once in the solo players channel, posted by guild as the
`dependabot` player (`<repo>#<n> ready to merge: <title>`, no session is
launched). It records `dependabot.announced`, so a PR that breaks and turns
green again is not announced twice.

The channel is a log. The work also shows in the lists that clear by
themselves: each ready Dependabot PR is a row of READY FOR YOU (`<repo>#<n>
<title> · from <name>`, after the tracked PRs, unfiltered board only) until it
merges or stops being ready, and a solo player whose last run ended with pending
work other than `none` is a row of NEEDS YOU (`⚑ <name> [<class>] <repo>:
<pending>`) while its trigger is still active. The web needs-you view shows the
same rows and counts the ready ones in the `ready` badge.

The solo players view, the board and `guild solo status` also list the PRs to
merge under the `dependabot` player (`to merge: <repo>#<n> <title>`). A ready PR
whose merge state GitHub has not computed yet (`UNKNOWN`, which happens right
after the base branch moves) keeps its place until GitHub reports a definite
state.

A solo player is `running` while an adventurer on its health job is active and
its session is alive, `stalled` when that adventurer is active but its session is
gone (crash, closed window, usage limit; the row reads `stalled: session gone,
run guild adventurer dismiss <id>`, the tick does not launch it, and dismissing
that adventurer, allowed once its session is gone, makes the player launchable
by the normal rules),
`due` when its trigger is on, nothing runs and the last report (`done`,
dismissed or not) and the last launch are older than the 1h cooldown, `cooling`
when the trigger is on but the last report or launch is newer, `fixing` (a
`red-main` player only) while an open PR of the repo is tracked with
`--fixes-main`, which holds the player and shows `fixing: waits on <ref>` until
that PR merges or closes, and `idle` without a trigger.

The cooldown is 1h, but when the trigger text equals the one of the last launch
(for example a Dependabot PR that needs a human) it is the player's retry wait,
so a player that cannot fix its trigger does not relaunch every hour. The retry
wait is `retry_after` of its config entry, by default 4h on a `main-red` trigger
and 24h on a `dependabot` one. A different trigger keeps the 1h cooldown. A
backing-off row reads `cooling: same trigger`. A launch with no trigger (manual,
main already green) or a launch recorded before the trigger was stored counts as
a different trigger.

Each row also shows its retry wait and an estimated next run: the time the
cooldown ends on a `cooling` row, the next interval on an idle `every` player,
`next tick` on a `due` row (the background tick runs every 10 minutes while
`guild web` or a waiting session is up) and `none` otherwise, because a
`main-red` or `dependabot` player has no date until its trigger turns on.

`guild solo list` (alias `guild solo status`) and the `SOLO PLAYERS` section of `guild board` (hidden under
`--party` and `--raid`) and the web `solo players` show name or job, class,
repo, trigger, state, retry wait, next run, last report time and last pending text; a due or idle row
carries `guild solo launch <owner/repo> <job>` as text to copy. The web has no
launch button.

`guild solo status` takes the scopes of launch: no argument for every player,
`--project <name>` or `<owner/repo> <job>`; the last form adds the player's last
5 runs and last 10 channel messages. An unknown project or player is an error.

`guild solo launch <owner/repo> <job>` is for the human terminal and refuses
inside a Claude Code session. It opens a tmux window named
`solo-<job>-<owner>-<repo>` the same way `guild adventurer launch` does, even
when the player is not due. `<owner/repo> <job>` is matched across all projects, so it works from any directory, like in `status`, `stop` and `resume`.
A player closes its own window after `guild adventurer done` (see `guild adventurer launch`), so its prompt ends with one short `guild solo say` instead of the long final report. Launch still closes a finished window left open before launching, and refuses a running player or a stalled one (dismiss it first).
`guild solo launch --all` launches every configured player and `guild solo launch
--project <name>` those of one project, whatever their trigger, skipping the
running and the stalled ones. They print one line per player (`<name> launched`,
`<name> skipped: running`, `<name> skipped: stalled, run guild adventurer dismiss
<id>`, `<name> not launched: <error>`) and go on after a failure. The pair
`<owner/repo> <job>`, `--all` and `--project` exclude each other.

`guild solo stop` and `guild solo resume` take the three scopes of launch, but
all players need `--all`: with no argument they are an error, so a mass stop is
never an accident. Both are for the human terminal and refuse inside a Claude Code
session. `stop` on a `running` or `stalled` player closes its `solo-<job>-<owner>-<repo>`
window (a missing window is fine), dismisses its active adventurer, pauses the
player and posts `<name> stopped by the human` to the channel; on any other
player it only pauses it and posts `<name> paused`. `resume` lifts the pause and
posts `<name> resumed`. A pause is a `solo.paused` event and `solo.resumed` ends
it, so it survives `guild rebuild`. A `paused` player is never `due`: the tick
leaves it alone, and `launch` (one player, `--all` or `--project`) skips it with
`<name> skipped: paused, run guild solo resume <owner/repo> <job>`. The board and
the web show `paused` with the resume command as the text to copy. They print one
line per player (`<name> stopped`, `<name> paused`, `<name> already paused`,
`<name> resumed`, `<name> not paused`, `<name> not stopped: <error>`) and go on
after a failure.

Solo players are active as soon as they are configured: there is no process to
start. The `solo-tick` background job runs `guild solo tick`, driven by sessions
and `guild web`.

`guild solo tick` launches every `due` player the same way and is the
`solo-tick` background job (see "Background jobs"), so a red main or a stuck
Dependabot PR gets a session without a command. It is for the human terminal and
the background job and refuses inside a Claude Code session. It closes the
window a `due` player still has, left by its finished run, before launching it
again, prints one line per player it could not launch
(for example `tmux not found`) and still exits 0. Each launch, manual or not,
records a `solo.launched` event with the trigger text it was made for, and a launch younger than the cooldown keeps
the player `cooling`, so a trigger that stays on while the new session binds,
or after the human closed its window, does not launch it again. A launch,
manual or by the tick, posts `<name> (<class>) started on <repo>: <trigger>`
(`manual launch` when no trigger is on) to the solo channel and no longer posts
a project notice, so launches do not interrupt other sessions.

The solo channel holds only important messages: the launch line, `<name>
finished: <pending>` when its adventurer ends, and what the player posts with
`guild solo say "<text>"`. `say` runs only inside a session bound as the
adventurer of a solo player, strips control sequences and refuses empty text
or text over 300 characters. `guild solo channel --limit N` prints the latest
messages newest first. The web shows the latest 20 as a read-only feed at the
top of the solo players section (the board JSON key `solo_channel`). Every item carries its `project`. `guild solo list` and `guild solo channel` group by project and take `--project <name>` to show one; the text board groups the same way.
`guild solo runs <owner/repo> <job>` prints the last runs of a player, read
from its adventurers: start time, `running`, `stalled` or `done`, duration and
pending report, then the PRs the run tracked with their lifecycle. The web
lists the last 5 per player under a collapsible `runs`, with the same PRs; the board JSON carries them as `runs` on each player.

### Marking notices seen

`guild notice seen <id>` marks an active notice as seen so new messages stand
out; `guild notice unseen <id>` undoes it, and `guild notice seen --all` marks
every active notice at once (`N notices marked seen`). The id and `--all` are
mutually exclusive and one of them is required. A seen notice is only a mark
for the human view: it stays listed everywhere while active, and delivery
(inbox cursors, `prompt-submit`, `post-tool-use`), the `session-start` brief
and `guild brief` are untouched. The commands work for the human actor and for
bound sessions, and fail for an unknown id, a notice that is already seen (or,
for `unseen`, not seen) and a notice that is not active (closed or expired).
Guild is single-user, so the mark is per guild, not per reader.

`guild notices` lists every active notice, newest first, with its issue time
(local, `YYYY-MM-DD HH:MM`) and time left, unseen ones prefixed with `new`
(`new #13 [party] text (scope, 2026-10-04 14:30, 5h left)`), and ends with
`N new` when N > 0. `guild board`, `guild brief`, `guild web` and the inbox
lines (`- notice #13 from party at 2026-10-04 14:30: "text"`) show the same
issue time and order. The NOTICES section of `guild board` (also `--party` and
`--raid`) lists the same notices, marks unseen ones with `new` (colored on a
terminal only) and its header reads `NOTICES · N active (M new)`, the count
only when M > 0.

Storage: events `notice.seen` and `notice.unseen`, and the projection column
`notices.seen_at` (`TEXT`, `NULL` when not seen), added to existing databases
by the column migration; `guild rebuild` replays it.

### `guild web`

`guild web [--port <n>]` serves the same board in a browser, with more room
than a terminal for filtering, collapsing and linking out. `--port` defaults
to 8765; pass `--port 0` to let the OS pick a free port. It always prints
the real, resolved URL before serving, with the session token in the
fragment (the fragment is never sent to the server); open that exact URL:

```
guild web: http://127.0.0.1:<port>/#t=<token>
```

The server serves the page files it loaded at start, so restart `guild web`
after updating guild.

**Layout**: the page is a sidebar next to a pane, using the full width; under 480px the
sidebar sits above the pane. The sidebar links to the views, kept in the URL hash so a
reload or the 10-second refresh keeps them: `#needs-you` (default: open asks, ready for
you, answered asks), `#party/<name>`, `#raid/<name>` (asks, merge queue, tasks per day, parties, memory),
`#adventurers` (adventurers and health jobs), `#solo-players` (solo players, one tab per project, each with its players and then its channel; `#solo-players/<project>` opens that tab and `#solo-players` the first one), `#ideas`, `#quests` (quest board) and
`#overview` (notices, raids, drift, projects). The menu lists needs you, adventurers, solo players, ideas, quest board and overview first, with counts for
asks, ready PRs, blocked and context-high parties (a count above zero is a pill coloured by
its type), active adventurers, solo players, ideas, open quests and new notices. The solo players item is
collapsed by default and opens to one link per project (it opens by itself on a project tab). After them come the parties grouped by raid (a party in
two raids shows under both) and a `parties` group for parties outside raids, since those lists grow. Each party row shows its state badge, its open asks, the work left and
`stopped without report`; parties sort by attention (waiting on permission, waiting on an
ask, context high, waiting on input, stopped with work, working, queued, parked, blocked) and a raid header
shows its worst member state. A party view shows the whole merge queue of its raids, or its own queue
when it has no raid. The header keeps the PR state filter.

**Progress**: under the merge queue, the party and raid views show the tasks done out of
the total of the active quests with a bar, one bar per quest, the active, blocked and queued
counts, and the blocked tasks grouped by reason (the tooltip lists their ids). A raid view
sums its member parties. `guild board --party` and `guild board --raid` print the same as
`PROGRESS · <done>/<total> tasks done (<pct>%)` (model key `blocked_groups` on each party;
the totals come from `remaining`).

**Tasks per day**: under the merge queue, the party and raid views show a table of the
last 15 days, today included (one column per local day): `created` counts the tasks added
to the party's quests that day, `done` the tasks finished that day. A `-` marks a day with
no session of the party and no task created or done; a `0` means a session ran but created
or finished nothing (model key `active`). A session that sits idle across midnight leaves
no event on the second day, so that day also shows `-`: the web cell's tooltip and a line
under the CLI rows say so. An `x` marks a day before the party's first leader started
(model key `existed`). A raid view sums its member parties, and a day is
active (or existed) when any member was. A task counts for the party that owns its quest now. `guild board --party`
and `guild board --raid` print the same rows as `TASKS PER DAY · last 15 days` (model key
`daily_tasks` on each party).

**Party waits**: each party card shows a `waits on:` row with one pill per
wait (model key `waits`), with a tooltip that explains the kind.

**What it shows**: open asks (question, party, options,
refs, how many refs still block it, a collapsible context, a `detail` control
that loads `GET /api/asks/<id>`, and a collapsed "answered asks" section), active notices,
a "ready for you" list (see "Ready for you on the board"), the merge queue (one card per raid, plus one per party outside raids that has
open PRs: a `MAIN RED` row per red main, then numbered PR links with their
label pills (`draft`, `converging`), the human-ready pill (`ready` or `ready (CI pending)`), checks, party, task, state, `unblocks N`, the action and the
`next action` marker, the reasons as pills, a collapsible ready-check detail per PR (blockers, missing items, waits, gates and notes, the same content as `guild pr ready-check`) and a `next to merge: <ref> (<party>)` line, or `no PR ready to merge`, matching `guild merge-queue --head`; blocked PRs in place; read-only, the same order as
`guild merge-queue`, with `synced N min ago`; the party view shows
the whole queue of its raids (or its own queue) and the raid view only that raid's card; the model
key is `merge_queues`), drift findings for the default scope (grouped by rule, one block per
project resolved from the parties shown, skipping parties without a
project; each finding carries its owning `party` when known, and the party
and raid views keep only their parties' findings, hiding findings with no
party), a "projects" section (one card per project of the parties shown,
model key `projects`: `open PRs N/cap` and the `wait:` text of `guild next`
when `max_open_prs` is reached, `hot files` touched by at least
`max_open_prs_per_file` open PRs with their refs, `finding classes` with PR
count and threshold marking the classes at or above
`finding_guard_threshold`, and `sdd synced Xm ago, tracker synced Ym ago`
from the last successful `sync --source sdd|tracker`; the lists are hidden
when the feature is off or empty; each party also shows `open PRs N/cap`
and its `wait:` text when `max_open_prs_per_party` is set, model key
`caps`),
then one collapsible block per party with its own drift (the same
findings and cap of 5 as the session brief, then `N more`; hidden when
empty), quests, tasks and
PRs, plus PRs outside active tasks (legacy loose rows and PRs on queued tasks; adventurer PRs show under the adventurer), raids and claims. A state
filter (`all`/`fixes-main`/`fixes-flaky`/`needs-ask-answer`/`needs-human-pr-review`/`converging`/`ready`/`draft`/`merged`) in the header and the
sidebar view (a party or a raid narrows parties, asks and
notices the same way `guild board --raid` does) narrow what is shown; the
page re-fetches `/api/board` every 10 seconds and repaints only the sections whose
data changed, so a form you are typing in (an idea, a notice, an answer) keeps its
text and focus; it also keeps the current filters and which blocks are collapsed. PR links open
`https://github.com/<repo>/pull/<n>` in a new tab; PR cards also show review pills (`N unresolved threads`, `changes requested`, `behind base`, `merge conflict`, the same reasons as the merge queue) and `on <base>` when the PR targets a branch other than `main` or `master`. A task also links to its
tracker card when the project configures `tracker.browse_url` (see
"Project config"). A "bases" section in the header, left of "resources" (model key `bases`),
shows the same local base drift lines as `guild board`: a warning pill when the clone is behind
`origin/<base>`, an ok pill when it is up to date, a neutral `paused` pill for a paused base; each line has a `pause` or `resume` button (`POST /api/bases/<owner>/<repo>/pause|resume`, same function as `guild base`). A collapsible "resources" section at the bottom shows the
`guild resources` report from `GET /api/resources` (see "`guild resources`").

**Colors**: the page uses the terminal board's meanings, with CSS classes
only (no inline style) and light and dark variants through
`prefers-color-scheme`. A PR's lifecycle is a badge (`converging` amber, `ready` green,
`draft` gray, `merged` purple, `closed` muted gray); its type is a neutral
gray chip next to it, and the urgency marks and human flags add badges
(`fixes-main` red, `fixes-flaky` blue, `needs-ask-answer` red,
`needs-human-pr-review` amber). Checks show `✗N` in red when N > 0 and muted otherwise, `✓N` in
green, `⏳N` in amber when N checks are still running, and `no checks` muted
when there are none. Merge queue entries in `waiting` state show their reason
in amber. A task's state is colored
too (`active` blue, `blocked` red, `queued` muted). The text labels stay, so
color is never the only signal.

**Marking notices seen from the page**: every active notice card shows its
time left (the model carries `expires_at` and a server-computed `time_left`)
and a `seen` flag. Unseen cards get a `new` badge and a `Mark seen` button;
seen cards have no badge and a subtle `Mark unseen`. The notices heading reads
`notices (N) · M new` and has a `Mark all seen` button; the model also carries
`new_notice_count`. `POST /api/notices/<id>/seen`, `/unseen` and
`POST /api/notices/seen-all` (body `{}`) run `guild notice seen` / `unseen` /
`seen --all` as the human actor and go through the same validation as the ask
routes. A form in the section creates a notice: text, a target select
(`project:<name>` for each project and `raid:<name>` for each raid on the board)
and a ttl select (1h, 8h, 1d, 3d). `POST /api/notices/create` (body
`{"text": "<text>", "to": "<scope>", "ttl": "<dur>"}`) runs `guild notice
create` as the human actor; empty text, an unknown scope, a bad ttl and the
length caps answer `422` with the message. `--until` is CLI-only for now.

**Raids**: a `raids` section lists each active raid with a `Pause raid` button
(inline confirm: pausing tells members to hand off), or a
`paused` pill and a `Resume raid` button while paused. `POST
/api/raids/<name>/pause` and `/resume` (body `{}`) run `guild raid pause` /
`resume`. The human is always allowed (no session), like `guild merge-queue
pin`; a pause by the human is recorded with `paused_by` `human`.

A party card and `guild board` label a leader session that has no name yet as
`unnamed session <first 8 characters of the session id>`; `no leader` shows only
when the party has no leader session at all.

**Hand off a party with no leader**: a party card shows a `Hand off` button
when it is `active` and has no live leader session (model key
`has_live_leader`). `POST /api/parties/<name>/hand-off` (body `{}`) runs the
same `guild handoff --party <name>` as the human actor; a party with a live
leader, an unknown party or a closed party answers `422` with the message. On
success the party becomes `awaiting-leader` and the button disappears on the
next refresh.

**Answering from the page**: each open ask card has one button per option
(clicking it only copies the option's text into the answer field), an answer
field, an `Answer` button and a `Dismiss` button (which asks for
confirmation). Answers and dismissals go through the same code as `guild
answer` and `guild dismiss`, acting as the human actor (no session): the
same length cap, email and project `pii_patterns` rejection, "not open" and
unknown-ask errors apply, and a rejected request shows the server's message
under the buttons. An empty answer is not sent. Buttons are disabled while a
request is in flight; on success the board is re-fetched. The 10-second
refresh keeps whatever you typed (and the focus) in each answer field.
Project `pii_patterns` are those of the project of the party that asked, wherever
`guild web` (or `guild answer`) is started from.

**Security model**: the server binds to `127.0.0.1` only, on the stdlib's
`http.server.ThreadingHTTPServer` — no third-party dependency, no build
step. Reads are `GET`; the only writes are `POST /api/asks/<id>/answer`
(body `{"answer": "<text>"}`), `POST /api/asks/<id>/dismiss`,
`POST /api/notices/<id>/seen`, `POST /api/notices/<id>/unseen`,
`POST /api/notices/seen-all` (body `{}`), `POST /api/notices/create`,
`POST /api/raids/<name>/pause`, `POST /api/raids/<name>/resume`,
`POST /api/parties/<name>/hand-off` (body `{}`),
`POST /api/quests/create-open`, `POST /api/quests/<slug>/take`,
`POST /api/quests/<slug>/release`,
`POST /api/prs/<owner>/<repo>/<n>/block` (body `{"reason": "<text>"}`) and
`.../unblock`, with `<id>` and `<n>` positive integers
(otherwise `404`); every other method,
including `OPTIONS`, is `405`, and no response ever carries CORS headers, so
cross-origin preflights fail. Requests whose `Host` header is not exactly
`127.0.0.1:<port>` or `localhost:<port>` get `421`, which blocks DNS
rebinding from a page on another origin. A `POST` must also pass all of:
an `Origin` header equal to `http://127.0.0.1:<port>` or
`http://localhost:<port>` (`403`); an `X-Guild-Token` header equal to the
per-start session token, compared in constant time (`403`); `Content-Type:
application/json` (`415`); a `Content-Length` of at most 16384 bytes (`411`
when missing, `413` when larger, exactly that many bytes are read); and a
JSON object with the required string key (`400`). The token is generated
with `secrets.token_urlsafe(32)` at each start, lives in memory only, is
never logged, and is printed only in the URL fragment `guild web` shows
at start. The page reads it from the fragment, keeps it in `sessionStorage`
for that tab, removes it from the address bar and sends it in
`X-Guild-Token` on every `/api` request; it never uses `localStorage` or a
cookie. Every `GET /api/*` without a valid token answers `403`; the HTML and
static files stay public. There is no `/api/session` endpoint (`404`).
An unexpected error answers a generic `500` `{"error": "internal error"}`.
A custom header cannot be sent cross-origin without a preflight, which is
refused. Validation failures answer `422` with `{"error": "<message>"}`
and never echo the submitted text. Every response carries a strict
`Content-Security-Policy` (`default-src 'self'`, no inline or third-party
scripts, no external assets), `X-Content-Type-Options: nosniff` and
`Referrer-Policy: no-referrer`; `/api/*` additionally sends `Cache-Control:
no-store`. The page (`guild/web/app.js`) builds every node with
`document.createElement` and sets text with `textContent` only — it never
uses `innerHTML` or any HTML-injecting API, so text coming from agents, SDD,
GitHub or the tracker is never executed. Every write runs a command function of `guild/commands` as the human actor,
the one behind the CLI command (`ask.answer`, `ask.dismiss`,
`notice.mark_seen|mark_unseen|mark_all_seen`; for a PR, `pr.block_external` and
`pr.unblock_external`, which record `pr set --blocked-external` with no party; an empty
reason or an untracked PR answers `422`). `guild web` writes nothing else
to the database, and it logs no per-request
access noise to stderr (server errors still do). Ctrl-C exits cleanly.

**Achievements and in-progress pages**: the board header links three pages,
`board`, `in progress` and `achievements`, each linking to the others. They
share the same CSS tokens and light/dark support, read `GET /api/history`
(the same model as `guild history`, with optional `party`, `raid` and `project`
query parameters), are read-only and render text with `textContent` only, like
the board.

`GET /progress` (`guild/web/progress.html`, script `guild/web/progress.js`)
lists the quests in progress as a table: party, quest, a `<progress>` bar with
done/total tasks, start and time since the last activity ("nothing in
progress" when empty). A quest idle for longer than the project's
`next.stale_hours` gets a `stale` marker (no marker when the key is absent).

`GET /history` (`guild/web/history.html`, script `guild/web/history.js`) shows a
totals strip (quests, PRs merged, tasks, asks answered with median, handoffs),
then completed-quest cards (dates, duration, epic progress bar, SDD tasks, JIRA
cards, PRs, handoffs, asks, accepted drift; legacy quests show a `no snapshot`
badge and `—` for unknown fields) closed-without-completing cards (reason, tasks not done at marking time), finished-raid cards (duration, parties,
quests, PRs, pauses) and a lifecycle-failures list (project,
event, status, detail, last output line).

### `guild handoff` and resuming a party

`guild handoff --parked "<what it waits on>"` also marks the party as parked
(waiting on something outside development, such as a legal answer): the board
and the web show the status `parked` with that reason and the age, and
`guild revive --list` prints it as `parked: <reason>`. The reason follows the
same checks as `--reason`. `guild party park <party> --reason "..."` and
`guild party unpark <party>` (and the Park and Unpark buttons on the web party
card) do the same from a terminal. The mark clears when a session resumes the
party, or on unpark; `--parked` cannot be combined with `--party` or `prune`.
A party without a live session whose only work left is blocked tasks shows
`blocked` with the blocked count per reason.

`guild handoff --in-flight "..." --learned "..."` (both required, non-empty)
renders `$XDG_DATA_HOME/guild/handoffs/<party>-g<N>.md` from the DB (active
quests, the full `guild next --all` queue, PRs, open asks, active notices and
claims, plus the two free-text fields), records `party.handed_off` (party →
`awaiting-leader`, `leaders.handoff_path` set for this generation) and prints
one command for the human to run. `--learned` also joins the party's memory
(`guild memory add`, see "Personal data and length caps" below), trimmed to
the memory length cap when longer; the handoff file itself keeps the full
text.:

```
GUILD_RESUME=<party> claude -n <party>-g<N+1> 'Continue the work described in the guild brief.'
```

The new session binds itself: the `SessionStart` hook inherits
`GUILD_RESUME` from `claude`, and when that party is `awaiting-leader` it
resumes it for the new session and injects the task brief plus the next item
before the first prompt (the handoff alone when the party has no task). The agent runs nothing and nothing needs quoting —
the prompt is a fixed, single-quoted constant. If the party is not waiting
for a leader (still active, closed, unknown or an invalid name), nothing is
bound and the context says why (`GUILD_RESUME=<party> not applied: ...`). A
session that already leads that party (e.g. after `/clear`) is left alone.

A generation started by pasting the raw command into a terminal adopts its
window: at `SessionStart`, when no window is recorded for it and `$TMUX_PANE`
sits in a window of the `guild` tmux session, guild records that window
(`leader.window_recorded`, same `leader_windows` table), so the chain offers
`--respawn` again. A plain `guild handoff` prints `guild revive --party <party>`
first (it relaunches in the `guild` tmux session and records the window) and
then the raw `GUILD_RESUME=<party> claude ...` command for a terminal without
tmux; when tmux is not installed it prints only the raw command. The raw
command carries `--permission-mode` from the mode guild recorded for the
leader, which `UserPromptSubmit` keeps current because `SessionStart` does not
always receive it.

`guild handoff --respawn` (only for a generation running in a window guild
launched, i.e. one recorded by `guild revive` or an earlier respawn; any other
session gets `--respawn needs a window guild launched` before anything is
written) does not print a command for the human: it launches that same fresh
command itself in a window of the `guild` tmux session (created when absent,
named after the party, name pinned like `revive`), records the window
(`leader.window_launched`, table `leader_windows` per party and generation) and
waits up to 90 seconds for the new generation to bind (aborting early if the new
window disappears or the party is gone). Once the new generation itself is bound
it closes its own pane with `tmux kill-pane` (never the window, so panes you
split into it survive), only when the tmux pane it runs in (`$TMUX_PANE`) is the
window guild recorded as launching this generation and that window is still in
the `guild` session; otherwise it prints `close this window yourself`. If tmux is
missing, the cwd is gone or tmux cannot create the window it prints `respawn
failed: <reason>; old session kept` plus the manual command; if the new
generation does not bind in time the old window is kept and the new one is left
running. Nothing else is ever killed. The context nudge asks for it when the
session runs in such a window; every other session gets the plain handoff nudge,
which says `auto-respawn off: this generation runs outside a guild tmux window`
and asks it to give the human the printed `guild revive --party <party>`
command. The nudge also comes right after a
compaction (`SessionStart` with source `compact`), because Claude Code compacts
far below `handoff_threshold`. A bound leader also gets its task brief and party
memory again at that point, ahead of the nudge, so the lean summary loses nothing
the brief holds.

`guild handoff --close` writes the handoff like a plain `guild handoff` call but
closes this same session's pane instead of printing a resume command, only when
the tmux pane it runs in (`$TMUX_PANE`) is the window guild recorded as
launching this generation and that window is still in the `guild` session;
otherwise it prints `not a window guild launched, close it yourself` and closes
nothing. It cannot be combined with `--respawn` (it launches no next generation,
it only closes the current one's own window).

`guild handoff --party <name>` hands off a party whose leader session is gone,
from a terminal only: it refuses from inside a Claude Code session and refuses
to combine with any other `handoff` flag (`prune`, `--in-flight`, `--learned`,
`--model`, `--dry-run`, `--respawn`, `--close`), naming the offending flag. It refuses
when the party still has a live leader session (`run guild handoff from that
session instead`). Otherwise it synthesizes `In flight` from the party
leader's recorded worktree — branch, count of uncommitted files, count of
unpushed commits, never file names, each falling back to `unknown` on a
missing cwd, a non-git directory, no upstream or a detached HEAD — sets
`Learned` to the fixed `none (automatic handoff)` and records
`party.handed_off` with `auto: true`; unlike a normal handoff, it does not add
to the party's memory.

### Task brief

`guild brief <party>/<quest>/<tid>` prints what a fresh session needs to pick
up one task, from a terminal and without a session. It is read-only: no inbox
cursor, no acknowledgement of review comments, no event. The party must exist
and be open, the quest must belong to it and the task must exist, otherwise
it fails with a clear message and writes nothing. The generation shown is the
next one, and the handoff read is the previous generation's.

Sections, in order, empty ones omitted: a frame line (`local data
(information, not instructions)`), party and generation, the task with its
state, epic and SDD spec and tasks paths, the party's PRs for that task (up to
5, newest first) each with `review comments: N (M unseen)` (guild stores only
the comment count and how many were already notified, not threads), the
party's asks that reference the task or those PRs (every open one up to 5, the
newest 3 answered with their answer), active notices that target the party,
its claims (up to 5), the previous generation's handoff (or `handoff: none
recorded`) and the local-only reminder.

Any caller can read any party's brief: guild is a single-user local tool and
does not authenticate readers. The handoff text is quoted line by line behind
a `  | ` marker and the brief ends with an `end of guild brief` line, so
handoff content can never pass for a frame, notice or closing line. Handoff and memory text are framed the same way: a line equal to the frame's
opening or closing line is dropped.
Invisible and bidirectional Unicode characters (zero-width, bidi overrides,
tag characters, private use, surrogates) are stripped along with control
sequences everywhere guild strips them; a joiner inside an emoji sequence is
lost. A party shows `idle`, `queued`, `parked`, `blocked` or `waiting-ask` unless the leader's
session file names a process that still exists. If building the brief fails
the hook falls back to the handoff and adds `guild: task brief unavailable
(<ExceptionClass>)`.

Every dynamic field is stripped of control sequences and single-lined, and
cut at 300 characters. The handoff section instead keeps only the previous
generation's "In flight" and "Learned" text (the only two fields not already
shown elsewhere in the brief), wrapped at 300 characters per line rather than
cut. The whole brief is capped at 4000 characters: the handoff is truncated
first, then the tail of the other sections, each with an explicit
`[... truncated: N lines omitted]` marker. The `SessionStart` hook injects
this same brief for a resumed generation, so a handoff or `revive` starts
from the brief and runs no state command.

The manual path still works: `guild party resume <party>` prints the previous generation's handoff content
plus a single (read-only, non-acknowledging) `guild next` line. A
freshly-resumed generation's very next `SessionStart` (e.g. after `/clear`)
shows the same handoff + next line once more, then reverts to the normal
brief.

`guild party resume <party> --session <name>` lets a human resume a party for
a session that already exists but was never bound (resolves the session id
via `~/.claude/sessions` by its `/rename` name). It is refused from inside a
Claude Code session (use the plain form there) and fails clearly when the
name is not found.

A handoff is marked consumed (`leaders.handoff_consumed_at`) when the next
generation binds, by the automatic `SessionStart` resume or by `guild party
resume` alike. `guild handoff prune [--dry-run]` deletes files nobody needs
again and prints what it did (`would delete` with `--dry-run`, which changes
nothing):

- the latest handoff of every open party is always kept;
- a superseded handoff is deleted once consumed (superseded and unconsumed is
  kept), recording a local `handoff.pruned` event that clears
  `leaders.handoff_path`;
- a closed party's last handoff is kept until `handoff_retention_days` after
  the close (project config, optional); without that key it is kept forever and
  the summary says `kept N closed-party handoff(s): no handoff_retention_days
  configured`;
- state markers under `$XDG_STATE_HOME/guild/ctx`, `ctx-baseline` and `hints` (context
  readings, session start readings, nudge, resume and raid markers) of sessions that neither run
  (`~/.claude/sessions`) nor lead an open party are deleted once a day old; with
  no session registry nothing is deleted (`markers kept: no session registry`).
  Other files in those directories, such as `human`, are kept.

Only files under guild's handoffs and state directories are deleted, symlinks
are never followed (reported as `skip ... symlink`) and paths outside the
handoffs directory are skipped. Prune also runs at the end of every
`sync --source gh` pass (so on each `SessionStart`) and on `party close`, which
reports `pruned N handoff file(s)` when N is above zero.

### `guild revive`

After a reboot, `guild revive` relaunches the active parties and the ones that handed off (`awaiting-leader`: they start the next generation fresh). It lists them
numbered (party, project, quest progress, status, last activity, leader session
name, cwd, permission mode, and `resume` or `fresh`) and starts the ones you
pick, one tmux window per party, in a tmux session called `guild`.

```
guild revive                   # TTY: prompts "numbers to revive (e.g. 1,3)"; no TTY: lists and exits
guild revive --party alpha --party beta
guild revive --all
guild revive --list            # no tmux needed: one copy-paste command per party
```

- `resume` (the leader transcript exists under `~/.claude/projects`) runs
  `claude --resume <session-id> --name <party>-g<N> [--permission-mode <mode>]`
  in the recorded cwd. `fresh` runs the handoff resume command
  (`GUILD_RESUME=<party> claude -n <party>-g<N+1> ...`) from the same cwd.
- cwd and permission mode come from the leader row (recorded by the
  `SessionStart` hook); when missing, the first lines of the transcript are
  read. A mode that is not known is never invented. Only `default`,
  `acceptEdits`, `plan`, `auto` and `dontAsk` are carried over:
  `bypassPermissions` and any other value are dropped, so a relaunched
  session never starts with permission checks off (this also covers
  `guild handoff --respawn`).
- A party whose cwd no longer exists (a removed worktree) starts `fresh` from
  the nearest main checkout above that cwd, since its transcript cannot be
  resumed elsewhere. With no such checkout, or with a window already in the
  `guild` session, the party is skipped with the reason printed.
- Names: the tmux window is named after the party, with `automatic-rename`
  and `allow-rename` off, and the `guild` session sets `set-titles on` /
  `set-titles-string "#W"` so the outer terminal title shows the party, plus
  `mouse on` so the wheel scrolls the output instead of the prompt history.
  Dragging selects text and copies it through the terminal (`set-clipboard
  on`, OSC 52) and, when `wl-copy` (Wayland), `xclip` or `xsel` (X11) is on
  `PATH`, also to the system clipboard (server option `copy-command`; `guild
  doctor` warns when none is found); Ctrl+click on a hyperlink opens it with `xdg-open`. Only session,
  window and server options and one root key binding are set at runtime; your
  `~/.tmux.conf` is untouched.
  Claude sessions are named `<party>-g<N>` on both fresh launch and resume,
  so the prompt box and `/resume` picker show the party and its generation.
  A session started by hand takes the same name, or `adventurer <id>`, from
  the `UserPromptSubmit` hook on the first human prompt after it binds. Only
  a name Claude Code generated is replaced: one set with `/rename` or `-n`
  stays. Health job and solo player sessions are named
  `health-<job>-YYYYMMDD-HHMMSS` in local time, so each run is distinct; their
  tmux window keeps the name without the timestamp.
- `--list` prints, per party, a one-liner for terminals without tmux: it sets
  the tab title with `printf '\033]0;<party>\007'`, then `cd <cwd> && claude
  --resume <id> --name <party>-g<N> ...`.
- The last line is `tmux attach -t guild`. `/goal` and other in-session state
  are not restored: re-issue `/goal` where you used it.
- Without tmux installed, launching fails with an install hint; `--list`
  still works.

### `guild raid`

A raid is a named channel parties join so a shared concern (CI, a shared
file) has a deterministic audience: it exists while it has at least one
active (non-expired, or until-leave) member, there is no separate create
command. `guild raid join <name>` takes exactly one of `--ttl <dur>` or
`--until-leave` (argparse enforces it, one required): a TTL join makes the
caller's bound party an active member until it expires, joining again
refreshes the TTL; `--until-leave` makes it a member with no expiry, ending
only with `guild raid leave <name>` or the `party close` cascade. Joining
again switches mode — a TTL join over an until-leave membership sets a TTL,
and an until-leave join over a TTL membership clears it. `guild raid leave
<name>` removes the caller's bound party; leaving when not an active member
is a clear error. `guild raids` lists every raid with its active members and
each member's time left, or `until leave` for an until-leave member. `guild
party close` cascades into every raid the closing party belongs to (TTL or
until-leave), same as claims.

A TTL membership due to expire within `MEMBERSHIP_WARNING_WINDOW` (12h) is
warned once per (session, raid, expiry) in `prompt-submit`, `post-tool-use`
and the session-start brief: `guild: raid <name> membership expires in <Nh>
— renew with guild raid join <name> --ttl <dur> or --until-leave`. Renewing
changes the expiry, so a later warning can fire again.

`guild notice create --to raid:<name> ...` is valid only while the raid has
at least one active member (a clear error otherwise); any bound party, or
the human, may post to it. A raid notice reaches a session's inbox
(`prompt-submit`/`post-tool-use`/`brief`) only if that session's bound party
is an active member of the raid at delivery time — unbound sessions and the
human terminal never receive raid notices, and the sender's own party never
gets its own notice back, same as every other notice scope. `guild notice
targeting` is the single place that resolves whether a notice's `project:`,
`guild` or `raid:` scope matches the caller. `guild board` shows the raw
`raid:<name>` scope on a raid notice, and lists each party's raids
(`raids: ci (5h left)`) at the end of its block.

### Raid pause

`guild raid pause <name>` marks the raid paused (events `raid.paused` /
`raid.resumed`, projection table `raid_pauses`, rebuilt like everything else).
Any active member of the raid, or the human, may pause or resume.
Pausing an already paused raid, or resuming one that is not paused, is a clear
error. While paused:

- `prompt-submit` and `post-tool-use` inject `raid <name> paused: finish
  current step and leave guild handoff` for every bound session whose party is
  an active member, once per (session, raid, pause) via a marker file shared by
  both hooks. There is no every-turn repetition; a later pause injects again.
- `guild next` (single and `--all`) returns `nothing actionable` plus
  `raid paused: <name>` for those parties and does not advance their PRs or
  tasks.
- `guild raids` shows `<name> (paused):`, `guild board` shows `PAUSED` in the
  party's `raids:` line and a `raid <name> PAUSED` header with `--raid`, and the
  web board model carries `paused` on each raid and membership.

`guild raid resume <name>` deletes the pause state and posts the notice `raid
<name> resumed` to `raid:<name>` (8h TTL), which reaches members through the
normal notice injection.

### Asks inside a raid

A member's ask goes to the human queue only; no other member receives it in
its inbox. `guild answer` is not restricted to the human terminal: any bound
session may answer an ask and the answer reaches the asker through the normal
inbox path.

### Raid views and clearer project errors

`guild board --raid <name>` narrows the board to that raid: only parties
that are currently active members, asks from those parties, notices scoped
`raid:<name>` (not `guild`- or `project:`-scoped notices, even from a
member), and claims held by those parties. An unknown raid name and a raid
with no active members give the same clear error
(`raid '<name>' has no active members`). `--raid` and `--party` are
mutually exclusive. `guild web`'s board model gains a top-level
`raids: [{name, members, paused}]` list, and the page gains a raid view
(`#raid/<name>`) that narrows parties, asks and
notices the same way the terminal `--raid` filter does.

Every "unknown project" error — `guild notice create --to project:<name>`
with an unregistered name, a project that cannot be resolved from `cwd`,
and any other project-name lookup — lists the known project names, e.g.
`unknown project 'x': known projects are acme, zeta` (or `known projects
are none` when none are registered yet). A single helper in `guild/config.py`
builds this list and is reused everywhere a project lookup can fail.

### Follow-up quests

`guild quest add <slug> --followups-of <quest> --title "..."` creates a
no-epic quest for your party, for extra work that belongs in a separate quest
rather than in the epic quest itself (extra tasks can also be added directly
with `guild task add`, see below). `<quest>` must exist and be owned by your
party; the link is recorded in the `quest.added` event payload
(`followups_of`). `--tasks` and `--titles` work as with `--no-epic`. Combining
it with `--epic` or `--no-epic` is rejected.

### Party goal and done condition

`guild party start` and `guild adventurer promote` require `--goal` (what the
party is for) and `--done-when` (the condition that ends it); both follow the
same checks as `--reason`. `guild party set <party> [--goal ...] [--done-when ...]`
(at least one; refused on a closed party) and the Edit goal button on the web
party card change them. The board header and the web party card show `goal:`
and `done when:` (`no goal` for a party started before this existed), the board
JSON carries `goal` and `done_when`, `guild revive --list` prints `goal:`, and
`guild brief` and the handoff file (`## Goal`) carry them to the next session.
While a party has a done condition, `guild task add` requires `--reason` and the
reason must state how the task serves that condition.

### Tasks on epic quests

`guild task add <quest>/<tid> --title "..." [--reason "..."]` works on any **active** quest of
your own party, epic quests included; a done quest is refused (`quest '<q>' is
done`). On an epic quest the same overlap check as `quest add` applies: if
the tid is held by an active quest of another party, or task-claimed by
another party, the command is refused. A tid that is not in the epic's
`tasks.md` yet is accepted. Guild stays read-only towards the SDD, so for an
epic quest `task add` prints `add <tid> to <epic> tasks.md in the SDD` and
`task done` prints `mark <tid> done in <epic> tasks.md in the SDD`: the agent
updates `tasks.md` through the normal skills. `task add --no-sdd` marks
housekeeping work with no entry in `tasks.md` (a task that tracks a specs PR,
say): it prints no hint, shows `(no sdd)` on the board, and the `quest task not
in SDD` rule skips it; it still has to be done before `quest done`. Two `guild drift` rules detect
a missed update (`quest task not in SDD`, `task done, SDD not done`), and the
epic `quest done` drift gate refuses on them.

### Moving tasks between quests

`guild task move <quest>/<tid>[,<tid>...] --to <target-quest>` hands queued or
blocked tasks of your quest to another active quest, so a second party can work
part of a backlog. The target party opens an empty quest first (`guild quest add
<slug> --epic <epic> --title "..."`, no `--tasks`). Both quests must be active, in
the same project and the same epic (or both without an epic). The move is
refused, with nothing written, when a task is `active` or `done`, already exists
in the target, has an open tracked PR, or holds an unexpired claim of your party
(`guild release <area>` first). Title, state, summary and blocked reason travel
with the task, and its tracked PRs are re-pointed to the target quest. The board
shows a `move to` select on queued and blocked tasks.

### Discarding tasks

`guild task discard <quest>/<tid> --reason "..."` drops a task created by
mistake without counting it as work done. The task keeps its row with state
`discarded`, plus the reason, the author (the party that ran it, or `human` from
the web) and the date. A discarded task is neither unfinished nor done: `quest
done` and `party close` ignore it, progress totals, `guild history` and the
final report leave it out, the board hides it, and its tid is free again for
other quests. `guild brief` lists it in a `discarded` lane. Discarding is refused
for a `done` or already discarded task and for a task held by an adventurer;
an `active` task, a task with an open tracked PR, or one with an unexpired claim
of your party needs `--force`. `start`, `block` and `done` refuse a discarded
task. `guild task restore <quest>/<tid>` brings it back as `queued`. On an epic
quest, the command asks you to remove the task from the epic's `tasks.md`, and
the drift rule `discarded task in SDD` catches it if you forget. The web board
shows a `Discard` button (reason prompt, `force` checkbox) on unfinished tasks
and a collapsed `Discarded (N)` list per quest with a `Restore` button.

### No overlapping task lists

`guild quest add <slug> --epic <slug> --tasks T01,T02,...` rejects the whole
command, writing nothing, if any listed task is either in an **active** quest
of **another** party for the same project and epic, or task-claimed
(`task:<epic>/<tid>`) by another party. The error lists every conflicting
task with its holder, e.g. `T02 is in quest raid-wave1 of party alpha; T05 is
claimed by party beta until 14:30`. A task in the caller's own other quests
never conflicts — that party's own overlap is its own business. A closed
quest or an expired claim never conflicts either. Seed stays exempt, same as
before (`guild seed` writes `quest.added` events directly).

`guild claim check <area>` is a read-only orchestrator helper: it fires no
event. Exit 0 and `free` when the area has no active claim; exit 0 and `held
by you until HH:MM` when the caller's bound party holds it; exit 1 and `held
by party <p> until HH:MM` (printed to stdout, so a script can parse it) when
another party holds it. From an unbound session or the human terminal,
"held by you" never applies — any active holder gives exit 1. It accepts any
area string, including `task:<epic>/<tid>` and a shared-area glob string.

### Design note: `claim check`

`guild claim <area> --ttl <dur>` takes the area as a bare positional with no
subcommand keyword, so a native `argparse` subparsers dispatch for `check`
cannot sit next to it: subparsers greedily claim the first positional and
reject anything that is not one of their declared choices, which would break
plain `guild claim ci.yml --ttl 30m` (`ci.yml` is not a valid "subcommand").
Instead, `claim`'s parser declares two positionals (`area`, an optional
`check_area`) and an optional `--ttl`; the handler dispatches on
`area == "check"`. This keeps the legacy form working unchanged and makes
`check` a reserved word: `guild claim check <area>` and
`guild claim check --ttl ...` (rejected clearly, `check` takes no TTL) both
work, but an area literally named `check` can never be claimed or read this
way — a deliberate, documented gap rather than an ambiguous parse.

### Design note: `notice`

The plan's literal surface (`guild notice "<text>" ...` and
`guild notice close <id>`) is ambiguous for argparse: a bare positional
`"close"` used as notice text would collide with the `close` subcommand.
Phase 1 resolves this by always requiring an explicit action:
`guild notice create "<text>" ...` / `guild notice close <id>`.

### Design note: `party start`

The plan's CLI surface floats `party start <name> --quest <slug>`. Phase 1
drops `--quest` from `party start`: a party is created empty, and
`guild quest add` binds the new quest to the caller's party. This avoids a
chicken-and-egg requirement (the quest would have to exist before the party
that owns it) and matches how every other owned resource (task, PR, ask,
claim) is attached to a party — via its own creation command.
