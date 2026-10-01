# agents-guild

A small, deterministic, project-agnostic CLI for coordinating several Claude
Code sessions working in parallel on the same codebase (or on several
codebases). State is validated and persisted by code, never hand-written in
prose. Local first. Python 3.10 stdlib only, no runtime dependencies.

`guild` gives you:

- A work board per party (quest, tasks, PRs, one line each).
- A single queue of decisions that need a human (`guild asks`).
- Broadcast notices between sessions ("pipeline is down, fix is PR #877").
- A PR registry reconciled against `gh`, not memory.
- Area claims so two sessions don't step on the same file.

Specs, plans and decisions for guild itself live in [`sdd/`](sdd/README.md) and
are updated in the same PR as the code.

## Glossary

- **guild** — one install: the database and config on this machine (or
  person).
- **party** — a durable work lineage that survives session handoffs. Session
  names change; the party does not. Owns quests, PRs and claims.
- **leader** — the current Claude Code session of a party. An attribute of
  `party`, not a command of its own.
- **quest** — a party's current assignment: a slice of an epic, a whole epic,
  or a stream with no epic at all (e.g. "fix CI costs").
- **epic** — a planning unit owned by external docs/trackers (out of scope
  for phase 1; guild never writes to it).
- **task** — a step of an epic, or a step of a no-epic quest. Guild tracks
  its work state (queued/active/blocked/done), not its plan.
- **raid** — a named channel several parties join for a shared concern (e.g.
  CI), so a notice can reach exactly that audience. Exists while it has at
  least one active (non-expired) member; join/leave with `guild raid
  join|leave`, post to it with `guild notice create ... --to raid:<name>`.

## Install

```
./install.sh
```

Symlinks `bin/guild` into `~/.local/bin/guild`. Make sure that directory is
on your `PATH`. Not run automatically by anything in this repo.

Hooks run `guild` in every session, so the installed copy must never be a
checkout you are editing: a half-written change goes live at once. If you
develop guild, install from a dedicated worktree that only moves to reviewed
commits:

```
git worktree add --detach ../agents-guild-live main
../agents-guild-live/install.sh
git -C ../agents-guild-live fetch && git -C ../agents-guild-live checkout --detach origin/main
```

After each merge, update the installed worktree with one command:

```
./update.sh ../agents-guild-live
```

It refuses if the installed worktree has local changes, moves it to
`origin/main`, lists the commits it brought, re-runs `install.sh` and runs
`guild doctor`. It never edits `~/.claude/settings.json` or project configs.

`guild doctor` checks, read-only, that every guild hook is wired in
`~/.claude/settings.json`, that `~/.claude/GUILD.md` exists and that every
project config loads; it exits 1 and names what is missing.

## Commands

```
guild whoami
guild init-project <name> --config <file.json>

guild party start <name>
guild party resume <party> [--session <name>]   # --session: from a human terminal only
guild party close [<party>] [--force]  # <party>: from a terminal, or your own party; --force overrides the raid-lead guard

guild quest add <slug> --title "..." --epic <slug> --tasks T09,T07b
guild quest add <slug> --title "..." --no-epic [--tasks A,B [--titles "First,Second"]]
guild quest add <slug> --title "..." --followups-of <quest> [--tasks A,B [--titles ...]]
guild quest done <slug>

guild task add <quest>/<tid> --title "..."          # no-epic quests only
guild task start <quest>/<tid> [--summary "..."]
guild task block <quest>/<tid> --reason "..."
guild task done  <quest>/<tid> [--summary "..."]

guild pr track <owner/repo>#<n> --task <quest>/<tid> --what "..." --waits "..."
guild pr set   <owner/repo>#<n> [--lifecycle draft|converging|needs-human|ready] [--waits "..."]

guild ask "<question>" --context "..." --ref <ref> [--ref <ref> ...] [--option "..." ...]
guild answer <id> "<text>"
guild dismiss <id>
guild asks

guild notice create "<text>" --to project:<name>|guild|raid:<name> --ttl <dur> [--until pr:<owner/repo>#<n>:merged|closed]
guild notice close <id>
guild notice seen <id>|--all
guild notice unseen <id>
guild notices

guild claim <area> --ttl <dur>          # area, or task:<epic>/<tid> / task:<quest>/<tid>
guild claim check <area>                # read-only, no event; exit 0 free/yours, exit 1 someone else's
guild release <area>
guild claims

guild raid join <name> --ttl <dur>      # the caller's bound party joins; joining again refreshes the TTL
guild raid join <name> --until-leave    # joins with no expiry; ends only on `raid leave` or `party close`
guild raid join <name> (--ttl <dur> | --until-leave) --lead  # also becomes the raid's lead
guild raid leave <name>
guild raids

guild next [--all]     # ranked action queue for the caller's party
guild handoff --in-flight "..." --learned "..."

guild merge-queue [--raid <name> | --party <name>]   # read-only: PRs in the order to merge by hand
guild merge-queue pin   <owner/repo>#<a> --before <owner/repo>#<b>
guild merge-queue unpin <owner/repo>#<a> --before <owner/repo>#<b>

guild board [--party <name> | --raid <name>]
guild web --port <n>
guild sync --source gh|sdd|tracker
guild sync-timer install --every <dur> | uninstall | print
guild drift [--epic <slug> | --all]
guild brief
guild inbox --since-last
guild statusline --session <id> [--ctx <pct>]

guild hook session-start   # reads Claude Code hook JSON on stdin
guild hook prompt-submit
guild hook post-tool-use
guild hook pre-push
guild hook pre-edit
guild hook pre-commit      # git hook: no stdin, session from CLAUDE_CODE_SESSION_ID

guild seed <file.json>
guild rebuild
guild export --visibility guild
```

Refs use two literal formats: `pr:<owner/repo>#<n>` and `task:<quest>/<tid>`.
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
every ref has resolved — a hint the ask can probably be dismissed.

### `guild next`

Deterministic, per-party ranking, evaluated in order:

1. Own PR with failing checks, a merge conflict (`mergeable == CONFLICTING`),
   or unseen review comments (`review_comment_count >
   last_notified_comment_count`).
2. Own PR whose lifecycle is `needs-human` and has an ask, referencing it,
   answered after the PR was last `pr set`.
3. Own PR `converging` with no activity for longer than the project's
   `next.stale_hours` (skipped entirely when that key is absent — no hidden
   default).
4. Next queued task of the caller's active quests, ordered by the observed
   `tasks.order_idx` (nulls last, then `tid`), whose dependencies (`tasks.deps`)
   all resolve `done` (see resolver below), that has no open ask referencing
   it and is not task-claimed by another party.
5. Raid lead work, only for a party that is the active lead of a raid: open
   asks from the raid's other member parties (`raid <name>: ask #<id> from
   <party>: "<question>"`), then the raid's merge queue entries for the other
   members' PRs, ready ones with their position and reason and blocked ones
   with their reasons (`raid <name>: merge queue <n>. <ref> <party> — <reason>`
   / `raid <name>: blocked <ref> <party> — <reasons>`). Without `--all` only
   the first item is printed. Read-only: guild never merges and nothing is
   acknowledged.
6. Nothing actionable: the exact blockers (pending deps and who says so, open
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
A party that leads a raid cannot be closed while that raid has other active
members (a member's open asks live and die with its membership): the command
fails naming the raid and the members, and `guild party close --force` closes anyway.
Closing cascades in the same event: the party's active quests become `done`,
its open asks are dismissed and its claims are released. Tracked PRs stay
tracked for history and are listed if still open. `guild quest done <slug>`
finishes one quest without closing its party. Closed parties leave the board
and quests that are `done` leave `guild drift`'s default scope.

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

`guild` has no daemon, so this only fires when someone runs the sync. A raid
lead should keep a watcher running for the duration of the raid, e.g.
`watch -n 300 guild sync --source gh` from a terminal, or `/loop 5m guild
sync --source gh` from a session that supports it.

### `guild sync-timer`

`guild` has no daemon. To keep `sync --source gh` fresh without running it by
hand, `guild sync-timer install --every <dur>` (same duration format as
`--ttl`, e.g. `10m`) writes two systemd user units,
`guild-sync-gh.service` (runs `guild sync --source gh`) and
`guild-sync-gh.timer`, into `$XDG_CONFIG_HOME/systemd/user` (default
`~/.config/systemd/user`), then runs `systemctl --user daemon-reload` and
`systemctl --user enable --now guild-sync-gh.timer`. `guild` must be on
`PATH`; the unit records its absolute path.

`guild sync-timer uninstall` disables the timer, removes both units and
reloads systemd. `guild sync-timer print --every <dur>` only prints the units
and writes nothing, for installing them by hand. `install` and `uninstall`
fail with a clear error when the platform is not Linux or `systemctl` is not
available; use `print` there. Nothing is pushed to running sessions: the timer
only refreshes the synced state that sessions read.

### `guild merge-queue`

`guild merge-queue [--raid <name> | --party <name>]` prints the open tracked
PRs that are ready to merge in the order to merge them, with the reason for
every position, plus the PRs that are not ready and why. It is read-only: no
network call, no event. **Guild never merges**: the output is advice for a
human, who merges by hand and re-runs the command after each merge (the
last line of the output says so).

**Scope.** `--raid` takes the open tracked PRs of the raid's active members,
`--party` those of one party; the two flags are mutually exclusive. Without a
flag, a bound session uses its raid when its party is in exactly one, errors
listing them when it is in several, and uses its own party when it is in
none; a human terminal (or an unbound session) must pass a flag.

**Ready or blocked.** A PR is ready when its lifecycle is `ready`, no check
is failing, `mergeable` is not `CONFLICTING`, and every task its own task
depends on (SDD `Depends on`, through the quest's epic) is done by the same
resolver `guild next` uses. Otherwise it goes to the `blocked:` section with
every reason that applies: `needs-human`, `draft` or `converging` (its
lifecycle), `checks failing (N)`, `merge conflict`, `waits on task Txx`.
Merged and closed PRs never appear.

**Hybrid order.** The ready PRs are put in a topological order over three
kinds of constraint, ties broken by PR number:

1. SDD task dependencies between the PRs' tasks.
2. Pins: explicit `X before Y` agreements (below). Pins and task dependencies
   are hard constraints; a pin that involves a merged, closed or blocked PR
   is ignored, so stale pins drop out by themselves.
3. Shared-area overlap: two ready PRs of the same repo that touch the same
   project `shared_areas` glob are sequential. By default the one with the
   smaller diff (additions plus deletions) goes first, then the one created
   earlier, then the lower number. This is a heuristic (a smaller change
   rebases less), never a rule: pin the pair to overrule it.

Every position carries its reason, for example:

```
merge queue · raid ci · synced 4 min ago
1. acme/app#1044  alpha  T01 — ready, checks ✓17; before acme/app#1047 (shares config/locales/es.yml, smaller diff)
2. acme/app#1047  beta   T02 — ready, checks ✓9; after acme/app#1044 (shares config/locales/es.yml)
blocked:
  acme/app#1049  beta  T03 — checks failing (2)
guild never merges: merge in this order by hand; re-run after each merge
```

A ready PR that must wait for an earlier one still sits in the list, with
`after <ref> (...)`. If pins and task dependencies contradict each other, the
PRs involved are listed as blocked with the cycle named rather than ordered
arbitrarily.

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
raid lead should keep the sync running (see "Merge notices").

**Pins.** `guild merge-queue pin <repo>#<a> --before <repo>#<b>` records that
`a` merges before `b` (event `merge_queue.pinned`, with the author party or
`human`; projection `merge_queue_pins`, rebuild-safe); `unpin` removes it
(`merge_queue.unpinned`). Both PRs must be tracked and open to pin. Who may
pin: when both PRs belong to members of the same raid, only that raid's lead
party or the human (also when one party owns both); otherwise only the party
that owns both PRs, or the human. The human is a session-less terminal; a
bound session acts as its party and an unbound session is refused. A pin that
would close a cycle with existing pins or task dependencies is rejected
naming the cycle (`pin would create a cycle: a -> b -> a`), a duplicate pin
and an `unpin` of a missing pin are errors. `unpin` still works after a PR
merges.

`guild board --raid <name>` starts with `next to merge: <ref>` and each party
block of `guild board` shows the same line for that party's own queue, when
one exists. `guild web` shows the same queues, see below.

### `guild drift`

`guild drift [--epic <slug> | --all]` reports, for the project resolved from
cwd, every disagreement between guild, SDD and the tracker that the last
`guild sync --source gh|sdd|tracker` observed. Read-only: it never fires an
event and never calls `gh` or `acli` — it only reads the projections a prior
sync filled.

Without flags, the report is scoped to work in progress: every epic-scoped
rule (`tracker and SDD disagree`, `SDD task without card`, `card not under
its epic`, `epic done with open work`) runs only on epics referenced by an
`active` quest of the project, and every PR rule (`merged PR, task not
done`, `PR open, card not started`, `PR closed unmerged`) runs only on PRs
tracked by a party that is `active` or `awaiting-leader`. `party has no
running leader` is unaffected by scope, always project-wide. `--all` drops
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
| `PR open, card not started` | a tracked PR is not merged/closed and its linked task's card has `status_category == new` |
| `PR closed unmerged` | a tracked PR has lifecycle `closed` |
| `party has no running leader` | an `active` party's `leader_session_id` is not the id of any session file under the Claude sessions dir (`awaiting-leader` parties are not findings) |
| `epic done with open work` | the epic's `sdd_status == done` but it still has a non-done quest task, or an open tracked PR linked to it |

The last line is `N findings` or `no drift`. `guild drift` never writes to
SDD or the tracker: fixing drift stays with humans and the normal skills.

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

`guild notices` lists every active notice with its time left, unseen ones
prefixed with `new` (`new #13 [party] text (scope, 5h left)`), and ends with
`N new` when N > 0. The NOTICES section of `guild board` (also `--party` and
`--raid`) lists the same notices, marks unseen ones with `new` (colored on a
terminal only) and its header reads `NOTICES · N active (M new)`, the count
only when M > 0.

Storage: events `notice.seen` and `notice.unseen`, and the projection column
`notices.seen_at` (`TEXT`, `NULL` when not seen), added to existing databases
by the column migration; `guild rebuild` replays it.

### `guild web`

`guild web --port <n>` serves the same board in a browser, with more room
than a terminal for filtering, collapsing and linking out. `--port` is
required; pass `--port 0` to let the OS pick a free port. It always prints
the real, resolved URL before serving:

```
guild web: http://127.0.0.1:<port>/
```

**What it shows**, in this order: open asks (question, party, options,
refs, how many refs still block it, a collapsible context), active notices,
the merge queue (one card per raid, plus one per party outside raids that has
open PRs: numbered PR links with their lifecycle badge, checks, party, task
and the reason of each position, then a `blocked` list; read-only, the same
order as `guild merge-queue`, with `synced N min ago`; the party filter keeps
only that party's PRs and the raid filter only that raid's card; the model
key is `merge_queues`), drift findings for the default scope (grouped by rule, one block per
project resolved from the parties shown, skipping parties without a
project), then one collapsible block per party with its quests, tasks and
PRs, plus PRs outside active tasks, raids (each with a `lead` badge when
that membership is the raid's lead) and claims. A party filter, a state
filter (`all`/`needs-human`/`converging`/`ready`/`draft`/`merged`) and a
raid filter (`all` plus one option per raid, narrowing parties, asks and
notices the same way `guild board --raid` does) narrow what is shown; the
page re-fetches `/api/board` every 15 seconds,
keeping the current filters and which blocks are collapsed. PR links open
`https://github.com/<repo>/pull/<n>` in a new tab; a task also links to its
tracker card when the project configures `tracker.browse_url` (see
"Project config").

**Colors**: the page uses the terminal board's meanings, with CSS classes
only (no inline style) and light and dark variants through
`prefers-color-scheme`. A PR's lifecycle is a badge (`needs-human` red,
`converging` amber, `ready` green, `draft` gray, `merged` purple, `closed`
muted gray). Checks show `✗N` in red when N > 0 and muted otherwise, `✓N` in
green, and `no checks` muted when there are none. A task's state is colored
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
routes.

**Answering from the page**: each open ask card has one button per option
(clicking it only copies the option's text into the answer field), an answer
field, an `Answer` button and a `Dismiss` button (which asks for
confirmation). Answers and dismissals go through the same code as `guild
answer` and `guild dismiss`, acting as the human actor (no session): the
same length cap, email and project `pii_patterns` rejection, "not open" and
unknown-ask errors apply, and a rejected request shows the server's message
under the buttons. An empty answer is not sent. Buttons are disabled while a
request is in flight; on success the board is re-fetched. The 15-second
refresh keeps whatever you typed (and the focus) in each answer field.
Project `pii_patterns` are those of the project of the party that asked, wherever
`guild web` (or `guild answer`) is started from.

**Security model**: the server binds to `127.0.0.1` only, on the stdlib's
`http.server.ThreadingHTTPServer` — no third-party dependency, no build
step. Reads are `GET`; the only writes are `POST /api/asks/<id>/answer`
(body `{"answer": "<text>"}`), `POST /api/asks/<id>/dismiss`,
`POST /api/notices/<id>/seen`, `POST /api/notices/<id>/unseen` and
`POST /api/notices/seen-all` (body `{}`), with `<id>` a positive integer
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
never logged or printed, and is served only by `GET /api/session`; the page
keeps it in a script variable, never in `localStorage`, a cookie or the URL.
A custom header cannot be sent cross-origin without a preflight, which is
refused. Validation failures answer `422` with `{"error": "<message>"}`
and never echo the submitted text. Every response carries a strict
`Content-Security-Policy` (`default-src 'self'`, no inline or third-party
scripts, no external assets), `X-Content-Type-Options: nosniff` and
`Referrer-Policy: no-referrer`; `/api/*` additionally sends `Cache-Control:
no-store`. The page (`guild/web/app.js`) builds every node with
`document.createElement` and sets text with `textContent` only — it never
uses `innerHTML` or any HTML-injecting API, so text coming from agents, SDD,
GitHub or the tracker is never executed. Apart from answering and dismissing
asks and marking notices seen or unseen, `guild web` never writes to the
database, and it logs no per-request
access noise to stderr (server errors still do). Ctrl-C exits cleanly.

### `guild handoff` and resuming a party

`guild handoff --in-flight "..." --learned "..."` (both required, non-empty)
renders `$XDG_DATA_HOME/guild/handoffs/<party>-g<N>.md` from the DB (active
quests, the full `guild next --all` queue, PRs, open asks, active notices and
claims, plus the two free-text fields), records `party.handed_off` (party →
`awaiting-leader`, `leaders.handoff_path` set for this generation) and prints
one command for the human to run. A party that leads a raid gets a `Role`
section in the handoff (`you lead raid <name>`), so the resumed session
knows it is the lead:

```
GUILD_RESUME=<party> claude -n <party>-g<N+1> 'Continue the work described in the guild handoff.'
```

The new session binds itself: the `SessionStart` hook inherits
`GUILD_RESUME` from `claude`, and when that party is `awaiting-leader` it
resumes it for the new session and injects the handoff plus the next item
before the first prompt. The agent runs nothing and nothing needs quoting —
the prompt is a fixed, single-quoted constant. If the party is not waiting
for a leader (still active, closed, unknown or an invalid name), nothing is
bound and the context says why (`GUILD_RESUME=<party> not applied: ...`). A
session that already leads that party (e.g. after `/clear`) is left alone.

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

### Raid lead

`guild raid join <name> (--ttl <dur> | --until-leave) --lead` makes the
caller's bound party the raid's lead. At most one lead per raid: a second
party's `--lead` join fails, naming the current lead
(`raid '<name>' already has a lead: party '<party>'`), while that lead is
still an active member. The same party re-joining with `--lead` is always
fine, and a plain renewal (no `--lead`) of an already-lead party keeps its
lead status — only the lead leaving (`raid leave`), its party closing, or
its membership expiring clears the raid's lead, after which the next
`--lead` join succeeds. The lead is shown everywhere raid membership is
shown: `guild raids` (`alpha (lead, 5h left)`), `guild board`'s party block
(`raids: ci (lead, until leave)`), `guild web`'s per-party raid list (a
`lead` badge) and top-level raid filter model, and every member's
session-start brief (`raid ci — lead: alpha`).

When a party that belongs to a raid creates an ask, the lead of each such
raid (if any, and not the asker) receives it once in its inbox
(`prompt-submit`/`post-tool-use`), framed the same way as other
cross-session messages: `- ask #N from <party> (raid <name>): "<question>"`.
The ask still goes to the human queue as always. `guild answer` is not
restricted to the human terminal — any bound session, including the raid
lead, may answer an ask and the answer reaches the asker through the normal
inbox path.

### Raid views and clearer project errors

`guild board --raid <name>` narrows the board to that raid: only parties
that are currently active members, asks from those parties, notices scoped
`raid:<name>` (not `guild`- or `project:`-scoped notices, even from a
member), and claims held by those parties. An unknown raid name and a raid
with no active members give the same clear error
(`raid '<name>' has no active members`). `--raid` and `--party` are
mutually exclusive. `guild web`'s board model gains a top-level
`raids: [{name, lead, members}]` list, and the page gains a raid filter
select (`all` plus one option per raid) that narrows parties, asks and
notices the same way the terminal `--raid` filter does.

Every "unknown project" error — `guild notice create --to project:<name>`
with an unregistered name, a project that cannot be resolved from `cwd`,
and any other project-name lookup — lists the known project names, e.g.
`unknown project 'x': known projects are acme, zeta` (or `known projects
are none` when none are registered yet). A single helper in `guild/config.py`
builds this list and is reused everywhere a project lookup can fail.

### Follow-up quests

`guild quest add <slug> --followups-of <quest> --title "..."` creates a
no-epic quest for your party, for extra work that does not fit an epic quest
(whose tasks cannot be added to). `<quest>` must exist and be owned by your
party; the link is recorded in the `quest.added` event payload
(`followups_of`). `--tasks` and `--titles` work as with `--no-epic`. Combining
it with `--epic` or `--no-epic` is rejected.

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

## Identity

Actor resolution: `CLAUDE_CODE_SESSION_ID` (or, for hooks, the `session_id`
field on stdin) → `leaders` table → party. An unbound session cannot write;
it gets refused with a hint to run `guild party start <name>` or
`guild party resume <party>`. Reads always work.

No session id at all (a plain terminal) resolves to the actor `human`,
allowed only for `answer`, `dismiss`, `notice create`, `notice close`,
`notice seen`, `notice unseen`, and all reads.

A project is resolved from the current working directory against every
project config's `paths` globs (first match wins, configs read in filename
order). Commands that need a project fail clearly when none matches.

**Trust model.** `guild` is single-user, same-OS-user software: hook stdin
(the `session_id`/`cwd`/`tool_input` JSON Claude Code writes) and the
`CLAUDE_CODE_SESSION_ID` environment variable are trusted at face value, by
design. Anything that can set that env var or write to that stdin already
runs as the same local user as `guild` itself, so there is no privilege
boundary to enforce between local processes — `guild` is not a sandbox and
does not attempt to be one.

Party, quest and project names are validated against a slug rule
(`^[A-Za-z0-9][A-Za-z0-9._-]*$`, no `..` anywhere) before they can become a
filesystem path (handoff files, project config files) — this is defense
against path traversal, not an identity boundary.

## Project config

`$XDG_CONFIG_HOME/guild/projects/<name>.json` (default
`~/.config/guild/projects/<name>.json`), installed via `guild init-project`:

```json
{
  "name": "acme",
  "paths": ["~/Documents/_projects/acme/*"],
  "github": {"repos": ["acme/app", "acme/docs"]},
  "sdd": {
    "root": "~/Documents/_projects/acme/sdd-docs",
    "epics_dir": "epics",
    "task_heading": "^#{2,3}\\s+(T\\d+\\w*)\\b.*?\\s[—–-]\\s+(.+)$",
    "key_ref": "[A-Z]{2,10}-\\d+",
    "deps_line": "^\\*\\*Depende de:\\*\\*\\s*(.+)$",
    "status_line": "^\\*\\*Status:\\*\\*\\s*(.+)$",
    "order_list": "^\\d+\\.\\s+(.+)$",
    "key_line": "^\\*\\*(?:JIRA|Jira):\\*\\*\\s*(.+)$",
    "epic_key_field": "jira",
    "epic_status_field": "status"
  },
  "tracker": {"kind": "jira-acli", "browse_url": "https://acme.atlassian.net/browse/"},
  "next": {"stale_hours": 8},
  "handoff_threshold": 80
}
```

`sdd.root` above can instead be `"git_repo": "~/Documents/_projects/acme/sdd-docs", "git_ref": "origin/main"` (see above) to read the same `epics_dir` from a git ref instead of a working copy.

- `sdd` (optional): drives `guild sync --source sdd`. Three independent,
  explicit regexes (`task_heading`, `key_ref`, `deps_line`, `status_line`) plus
  optional `order_list` and `key_line`; no hidden defaults, no fallback shape. A
  `tasks.md` file with zero `task_heading` matches is reported unparseable
  and skipped; other files still sync; `guild sync` exits non-zero if any
  file failed. See "SDD parsing rules" below for exactly how each regex is
  used.
  - Two mutually exclusive ways to read `epics_dir`, exactly one required:
    - `root`: a plain checkout path. `guild` reads `tasks.md` files straight
      off disk, so the checkout must exist and stay put.
    - `git_repo` + `git_ref` (e.g. `"origin/main"`), both required together:
      `guild` runs `git -C <git_repo> fetch --quiet origin`, lists
      `tasks.md` files at `<git_ref>` with `git ls-tree` and reads each with
      `git show <git_ref>:<path>` — it never checks out, resets or otherwise
      touches `git_repo`'s working tree, so it is safe to point at a clone a
      human or another session is actively using. A failed fetch, an unknown
      ref, or zero `tasks.md` files under `epics_dir` at that ref is a clear
      error, never an empty sync. `epics.sdd_path` is stored as
      `git:<git_ref>:<path>` in this mode. Prefer `git_repo`/`git_ref` for a
      docs repo shared with other sessions — the worktree guild reads from
      can otherwise be deleted or switched out from under it by someone
      else's cleanup, and `sync` would silently read nothing.
  - `epic_key_field` (optional): the frontmatter key (a plain `key: value`
    line between the leading `---` markers of the epic's `tasks.md`) that
    names the epic's own tracker card, e.g. `jira: DEMO-1`. Stored as
    `epics.jira_key`. Absent field, or no frontmatter at all, gives `NULL` —
    never guessed from the epic slug.
  - `epic_status_field` (optional): the frontmatter key that carries the
    epic's own SDD status, e.g. `status: done`, parsed exactly like
    `epic_key_field` and stored as `epics.sdd_status`. Absent field, or no
    frontmatter at all, gives `NULL`.
- `tracker` (optional): drives `guild sync --source tracker`. `kind` is
  required when this block exists; only `"jira-acli"` is supported today,
  anything else is a clear error. See "Tracker sync" below.
  - `browse_url` (optional, explicit — no hidden default): the base URL
    `guild web` prepends to a task's tracker key to build its card link
    (`browse_url + key`, e.g. `https://acme.atlassian.net/browse/DEMO-1`).
    Validated when the config is loaded: it must start with `https://`,
    otherwise `guild init-project`/every command that loads the project
    fails with a clear error. Absent → tasks never carry a `card_url`.
- `next.stale_hours` (optional): threshold for `guild next` tier 3
  (`converging` PR with no activity). Absent → that tier is skipped, never
  defaulted.
- `handoff_threshold` (optional): context-usage percent (0-100) at or above
  which `UserPromptSubmit`/`PostToolUse` hooks nudge once per session toward
  `guild handoff`. Absent → no nudge.
- `pii_patterns` (optional): list of explicit regexes, no hidden defaults.
  Checked, in addition to the built-in email pattern, against notice text,
  ask question/context, answer text and handoff `--in-flight`/`--learned` for
  the caller's project. A match rejects the command with an error that names
  the field, never the matched text.
- `shared_areas` (optional): list of glob strings relative to the repo root
  (e.g. `config/routes.rb`, `db/migrate/*`, `config/locales/*.yml`), matched
  with `fnmatch` against POSIX-style relative paths by `guild hook pre-edit`
  (see "Hooks"). Present → `shared_area_claim_ttl` is required, or the config
  fails to load.
- `shared_area_claim_ttl` (required together with `shared_areas`): the TTL
  (`30m`/`8h`/`3d`) the pre-edit guard claims a matched area for.
- `migration_paths` (optional): list of glob strings relative to the repo root
  (e.g. `db/migrate/*`), matched with `fnmatch` against changed file paths.
  Unset → the migration clash check is skipped and no extra `gh` call is made.
  Set → see "Migration version clash" under `sync`.
- Unknown top-level keys are allowed.

### SDD parsing rules

- `task_heading` matches a `##`/`###` line; group 1 is the tid, group 2 the
  title. Match lazily up to the **first** spaced dash after the tid (`.*?\s[—–-]\s+`),
  so a `→ KEY` or `(KEY)` connector before it is skipped and hyphens inside the
  title (`cross-tenant`, `(KEY-12)`) are kept.
- `key_ref` is searched (not matched) against the heading line first; a
  generic token pattern such as `[A-Z]{2,10}-\d+` covers `→ KEY`, `(KEY)` and
  `· KEY` connectors. A key in the heading always wins.
- `key_line` (optional) matches a body line such as `**JIRA:** KEY`; when the
  heading has no key, `key_ref` is searched in its group 1 and the **first**
  key found is the task's key (`**JIRA:** KEY-12 — moved under KEY-3` gives
  `KEY-12`; a markdown link `[KEY-12](…/browse/KEY-12)` works too). A matching
  line with no key token gives no key.
- `deps_line`/`order_list` are matched per body line; whichever line matches
  contributes its tid tokens via a fixed `T\d+\w*` token search, never a
  strict CSV split — prose around the ids (`T01 (gate — ...), T14`) and
  repeated mentions of the same tid are both handled; a bare `—` (or any line
  with no tid tokens) means no deps / no explicit order for that task.
  `order_list` is optional; without it every task's `order_idx` is `None`.
- `status_line` is matched per body line; only a literal `[x]` checkbox
  counts as done. Anything else — `[ ]`, free text with no checkbox, or no
  matching line at all — is pending. This is a deliberate simplification: SDD
  files that write `**Status:** done` in prose without a checkbox still read
  as pending until the checkbox is ticked.

### Tracker sync

`guild sync --source tracker` (adapter `guild/adapters/jira_acli.py`, `acli
jira workitem search`, list-form subprocess, never a shell) is read-only and
observes, for the caller's project:

1. For every observed epic with a `jira_key` (`epics.jira_key`, from
   `sdd.epic_key_field`), its children (`parent = <EPIC>`). Those cards get
   `parent_key = <epic key>`.
2. Every task `jira_key` not already seen as a child, plus every epic key
   itself, fetched by key in chunks of 50 (`key in (A,B,...)`). Those cards
   get `parent_key = NULL` — meaning "not a child of its epic" (or, for an
   epic card, simply itself), not "no parent in the tracker".
3. Each card's `key`, `fields.status.name`, `fields.status.statusCategory.key`
   (`new`/`indeterminate`/`done`) and `fields.issuetype.name` are stored in
   the `cards` projection (`project, key, status, status_category,
   issue_type, parent_key`), replaced wholesale for the project on every
   sync (snapshot semantics, rebuild-safe).

A key that fails `^[A-Z][A-Z0-9]+-\d+$` is never interpolated into JQL: it is
reported (`<KEY>: invalid tracker key`) and skipped. A key requested but not
returned by the tracker is reported as `<KEY>: not found in tracker`. A
non-zero `acli` exit or unparseable JSON is reported per query
(`<KEY>: <stderr>` for a failed children query, `tracker query failed: ...`
for a failed by-key query) and **nothing is written**: a partial snapshot
would delete cards that were not fetched and would record an epic's children
as "not a child of their epic". The previous snapshot is kept and the output
says `tracker snapshot not updated: previous cards kept`. Invalid and
not-found keys do not block the write. Any of these failures makes
`guild sync --source tracker` exit non-zero, same as `gh`/`sdd` sync.

## Storage

Append-only `events` table (SQLite, WAL, `busy_timeout=5000`, writes wrapped
in `BEGIN IMMEDIATE`) plus projection tables kept in sync in the same
transaction: `parties`, `leaders`, `quests`, `quest_tasks`, `epics`, `tasks`,
`prs`, `cards`, `asks`, `notices`, `claims`, `raid_members`, `pr_shared_areas`,
`merge_queue_pins`, `cursors`. `guild rebuild` drops every
projection and replays all events from scratch — the only exception is
`cursors`, which is a per-session read position, not domain state, and is
left untouched by rebuild.

`epics`/`tasks` are observed-only (never written by a guild command): they
hold whatever `guild sync --source sdd` last read, keyed by
`(project, epic)` / `(project, epic, tid)`. `cards` is likewise observed-only,
holding whatever `guild sync --source tracker` last read, keyed by
`(project, key)`, fully replaced on every sync. `leaders.handoff_path` and the
PR activity columns (`prs.mergeable`, `prs.review_comment_count`,
`prs.last_notified_comment_count`, `prs.last_activity_at`) were added by a
schema migration (`schema._add_column_if_missing`, `ALTER TABLE ... ADD
COLUMN`, guarded by `PRAGMA table_info`) that runs on every `db.connect`, so
a pre-existing database picks them up in place — no separate migrate step,
no data loss. Old events recorded before `mergeable`/`review_comment_count`
existed lack those payload keys; `guild rebuild` tolerates that (carries the
current stored value forward instead of raising) so historic databases
replay cleanly.

Default paths (all overridable via env, useful for tests):

- DB: `$XDG_DATA_HOME/guild/guild.db` (default `~/.local/share/guild/`).
- Config: `$XDG_CONFIG_HOME/guild/` (default `~/.config/guild/`).
- State: `$XDG_STATE_HOME/guild/` (default `~/.local/state/guild/`).
- Claude sessions: `$GUILD_CLAUDE_SESSIONS_DIR` (default `~/.claude/sessions`).

`guild` sets `umask 0o077` at CLI entry and explicitly `chmod`s the DB file
(and its `-wal`/`-shm` siblings) to `0600` and the DB, state, handoffs and
projects-config directories to `0700` on every `guild` invocation — this
also repairs a pre-existing world-readable DB from before this hardening.

## Personal data and length caps

Notice text, ask question/context, answer text and handoff
`--in-flight`/`--learned` are broadcast to every session and can be exported
(`guild export`), so they carry explicit length caps and a screen against
personal data:

- Length caps (`GuildError` if exceeded): notice text 500, ask question 300,
  ask context 2000, answer 1000, handoff `--in-flight`/`--learned` 4000 each.
- An embedded email address is always rejected.
- A project's `pii_patterns` (see "Project config") are checked too, scoped
  to the caller's project; for an answer, to the project of the party that asked.
- Every successful `notice create`, `ask` and `handoff` prints one reminder
  line afterward: never put names or identifiers of real people (students,
  guardians, staff) in these fields — use ids and roles instead.

Free text is also sanitized on the way in (ESC sequences, C0/C1 controls
except `\n`/`\t`, DEL are stripped when the event is recorded) and again at
`board` render time, as defense for data stored before this sanitizer
existed. Text rendered on a single hook or inbox line additionally collapses
`\n`/`\t` to spaces, so embedded newlines cannot forge extra lines.

## Seed schema

`guild seed <file.json>` loads state through the normal event path (so
`guild rebuild` reproduces it). Seeded PRs skip the `gh` existence check
(payload flag `seeded: true`); seeded epic-quest tasks skip the "tid must
exist in the synced `tasks` table" check that `guild quest add --epic ...`
enforces (seed writes `quest.added` events directly, bypassing that
command).

```json
{
  "parties": [
    {"name": "alpha", "project": "acme", "session_name": "2026-01-10-billing"}
  ],
  "quests": [
    {
      "slug": "billing-wave1",
      "project": "acme",
      "party": "alpha",
      "epic": "billing-revamp",
      "title": "Wave 1 of billing-revamp",
      "tasks": [
        {"tid": "T09", "title": "Invoice numbering", "state": "active", "summary": "in review"},
        {"tid": "T04", "title": "Tax rounding", "state": "queued"}
      ]
    }
  ],
  "prs": [
    {
      "repo": "acme/app",
      "number": 894,
      "party": "alpha",
      "task_quest": "billing-wave1",
      "task_tid": "T09",
      "what": "Sequential invoice numbers per tenant",
      "waits": "decide one more review round",
      "lifecycle": "needs-human"
    }
  ],
  "asks": [
    {
      "party": "alpha",
      "question": "One more round on #894?",
      "context": "numbering resets per tenant, not per fiscal year",
      "refs": ["pr:acme/app#894"],
      "options": ["extra round", "ship as is"]
    }
  ],
  "notices": [
    {"party": "alpha", "text": "CI fails on registry quota, fix is acme/app#877", "scope": "guild", "ttl": "8h"}
  ]
}
```

## Agent rules

`GUILD.md` holds the instructions agents need to use guild (bind, track PRs, ask, notice, claim). `install.sh` links it to `~/.claude/GUILD.md`; add one line to `~/.claude/CLAUDE.md` so every session loads it (absolute path, so it resolves the same even when `CLAUDE.md` is itself a symlink):

```
@~/.claude/GUILD.md
```

The rules ship with the CLI, so they change in the same commit as the commands they describe.

## Hooks

Wired from `~/.claude/settings.json` (not part of this repo):

```json
{
  "hooks": {
    "SessionStart": [
      {"hooks": [{"type": "command", "command": "guild hook session-start"}]}
    ],
    "UserPromptSubmit": [
      {"hooks": [{"type": "command", "command": "guild hook prompt-submit"}]}
    ],
    "PostToolUse": [
      {"hooks": [{"type": "command", "command": "guild hook post-tool-use"}]}
    ],
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [{"type": "command", "command": "guild hook pre-push"}]
      },
      {
        "matcher": "Edit|Write|MultiEdit|NotebookEdit",
        "hooks": [{"type": "command", "command": "guild hook pre-edit"}]
      }
    ]
  }
}
```

**Commit guard (git).** `pre-edit` only sees the Edit/Write family of tools.
Agents that write files through Bash (`cat > file <<EOF`, `python3 -`,
generators) never trigger it — observed in the first real raid, where the
`coder` subagents made every change with Bash. `guild hook pre-commit` closes
that gap at commit time, whatever wrote the file: it reads the staged paths
(`git diff --cached --name-only`), and for the caller's bound party (from
`CLAUDE_CODE_SESSION_ID`, which the Bash tool passes to git) claims every
staged shared area, or exits 1 naming the holder when another party holds
one (nothing is claimed then). Unbound sessions, human commits, projects
without `shared_areas` and anything outside git pass untouched; internal
errors print `guild hook error: ...` and never block the commit. It never
reads stdin.

Claims taken by either guard are released when the holder's PR that touched
them is merged, as seen by `guild sync --source gh` (see "Merge notices"), so
the raid lead's `/loop` sync is what frees the area for other parties before
the TTL runs out.

Wire it without touching the project's repository. With husky (it sources a
per-user init file before every hook, with the hook name in `$n`):

```sh
# ~/.config/husky/init.sh
if [ "$n" = "pre-commit" ]; then
  /home/<you>/.local/bin/guild hook pre-commit || exit 1
fi
```

Without a hooks manager, add the same call to the repository's
`.git/hooks/pre-commit` (shared by all its worktrees).

- `session-start`: prints `guild brief` to stdout (becomes context), then
  spawns `guild sync --source gh` in the background, detached. If this
  session was just bound as generation N > 1 (i.e. a resumed party) and this
  generation's handoff has not been shown yet, it is prepended once, together
  with a single read-only `guild next` line, ahead of the normal brief — this
  also covers a `SessionStart` refire (e.g. after `/clear`) within the same
  resumed generation.
- `prompt-submit`: prints only events new since this session's cursor
  (notices, answers/dismissals of this party's asks). Unbound sessions also
  get the binding hint, once. If a project `handoff_threshold` is configured
  and the last `guild statusline --ctx <pct>` recorded for this session is at
  or above it, nudges once per session toward `guild handoff`. Local DB only,
  no network.
- `post-tool-use`: the same new-events-since-cursor and context-threshold
  nudge as `prompt-submit` (sharing the same cursor, so nothing is reported
  twice across the two hooks), emitted as
  `{"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "..."}}`;
  completely silent (no output at all) when there is nothing new. Both hooks
  run in well under 100ms against a local SQLite DB.
- `pre-push`: inspects `git push` commands before they run (including
  `env`/`command`/`sudo`-wrapped, `VAR=val`-prefixed, `bash -c`/`sh -c`
  nested, and `&&`/`;`/`||`-chained forms); blocks pushes to a branch whose
  only PRs are merged/closed. When a push is detected but its branch or
  directory cannot be determined (bad `-C` dir, detached HEAD, unparseable
  command), it warns via `systemMessage` instead of allowing the push
  unverified. For a bound session in a project with `shared_areas`, it also
  lists the files in the push diff (`git diff --name-only <origin/HEAD>...HEAD`)
  and applies the same rule as `pre-commit`: every matching glob is claimed
  (`area:<glob>`), or the push is denied naming the holder when another party
  holds one. If the base branch (`origin/HEAD`) or the diff cannot be
  resolved, it warns via `systemMessage` and does not check `shared_areas`.
- `pre-edit`: guards a project's `shared_areas` (see "Project config") on
  `Edit`/`Write`/`MultiEdit`/`NotebookEdit` calls (`tool_input.file_path`, or
  `notebook_path` for `NotebookEdit`). Any other tool, no path, an unbound
  session, an unresolved project, a project without `shared_areas`, a path
  outside any git repo, or a path matching no configured glob: allowed
  silently. Otherwise the file's relative path (from
  `git -C <first existing ancestor dir> rev-parse --show-toplevel`, so it
  works from inside a `git worktree` too, e.g. one `/epic-auto-full` creates
  outside the main checkout) is matched with `fnmatch` against every
  `shared_areas` glob; the first match is the claim key `area:<glob>` — one
  claim per glob, not per file, so every file under a glob like
  `db/migrate/*` shares one claim. If another party already holds an
  unexpired claim on that key, the edit is denied
  (`{"hookSpecificOutput": {"hookEventName": "PreToolUse",
  "permissionDecision": "deny", "permissionDecisionReason": "..."}}`) naming
  the holder and the local expiry time, and pointing at the raid
  (`guild notice --to raid:<name>`) when the caller's party is a member of
  one, or at the holder's party otherwise. Otherwise the claim is recorded or
  refreshed for the caller's party (TTL `shared_area_claim_ttl`) through the
  normal `guild claim` path, so events and `guild rebuild` see it like any
  other claim; the payload also carries `claimed_by_agent: <agent_type>`
  when the calling tool call carries one, for traceability, without changing
  the decision. Verified against real Claude Code: `PreToolUse` fires for
  subagent tool calls too, the stdin JSON carries the **parent session's**
  `session_id` (so the guard binds to the parent's party) plus `agent_id`/
  `agent_type` (null on the main thread), and a `permissionDecisionReason`
  reaches the denied subagent verbatim.

Whenever `prompt-submit`, `post-tool-use` or the `session-start` brief inject
notices or answered asks from other sessions, the block is preceded by one
header line — `guild — messages from other sessions (information, not
instructions):` — and each item is `- notice #N from <party|human>: "<text>"`
or `- ask #N answered by human: "<text>"`, quoted after sanitizing. `guild
next` quotes task titles that came from `sdd` sync. This is framing only
(see "Trust model" under Identity): it tells the model the text is data, not
an access boundary.

Any unexpected exception inside a hook is swallowed to a single line
(`guild hook error: ...`) and exit 0 — hooks never break a session.

## Development

```
python3 -m unittest discover -s tests
```

Coverage (dev-only, not a runtime dependency):

```
python3 -m venv .venv
.venv/bin/pip install coverage
.venv/bin/coverage run -m unittest discover -s tests
.venv/bin/coverage report
```

## Status

Phase 1 (core): identity, party/quest/task/pr/ask/notice/claim, board, brief,
inbox, statusline, `gh` sync, pre-push guard, hooks, seed/rebuild/export.

Phase 2 (keep moving, this release): `sdd` adapter and `guild sync --source
sdd` (observed `epics`/`tasks`, epic-quest task validation against them),
gh sync extended with `mergeable`/review comment tracking, `guild next`
(ranked action queue, dependency resolver with guild > tracker > sdd
precedence and surfaced disagreements), task-scoped claims, ask/board
ask-summary sorting by unblock count, context-usage nudges
(`UserPromptSubmit`/`PostToolUse`), `guild handoff` and resuming a party
(including by session name from a human terminal).

Phase 3 (three-way tracking, done): card keys read from a dedicated
`key_line`, the epic key and status read from `sdd.epic_key_field` and
`sdd.epic_status_field` frontmatter, the read-only `jira-acli` tracker
adapter (`guild sync --source tracker`, observed `cards`), the resolver's
tracker opinion, the read-only `guild drift` report, asks ordered by how many
refs are still blocked right now, and `raid` (`raid join|leave`, `guild
raids`, notices scoped `--to raid:<name>`) are done.

**Idle-session wake: no-go (spike, this release).** The design considered
having a resumed leader auto-spawn (`claude -n ...`) instead of asking a
human to run one command. Not built: the mechanism that could plausibly wake
or drive a specific Claude Code session from the outside is the per-session
socket under `~/.claude/`, which is undocumented internal IPC with a
per-session private key — not a public contract. Building against it now
would mean guild's core handoff flow depends on an implementation detail
that can change without notice. `guild handoff` instead prints the one
`GUILD_RESUME=<party> claude -n <party>-g<N+1> '...'` command for a human (or an orchestrating
agent) to run; revisit auto-spawn if a public, documented session-control
contract appears.
