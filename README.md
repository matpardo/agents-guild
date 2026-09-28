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
- **raid** — a named channel several parties join for a shared concern.
  Phase 2, not implemented yet.

## Install

```
./install.sh
```

Symlinks `bin/guild` into `~/.local/bin/guild`. Make sure that directory is
on your `PATH`. Not run automatically by anything in this repo.

## Commands

```
guild whoami
guild init-project <name> --config <file.json>

guild party start <name>
guild party resume <party> [--session <name>]   # --session: from a human terminal only
guild party close

guild quest add <slug> --title "..." --epic <slug> --tasks T09,T07b
guild quest add <slug> --title "..." --no-epic

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

guild notice create "<text>" --to project:<name>|guild --ttl <dur> [--until pr:<owner/repo>#<n>:merged|closed]
guild notice close <id>
guild notices

guild claim <area> --ttl <dur>          # area, or task:<epic>/<tid> / task:<quest>/<tid>
guild release <area>
guild claims

guild next [--all]     # ranked action queue for the caller's party
guild handoff --in-flight "..." --learned "..."

guild board [--party <name>]
guild sync --source gh|sdd
guild brief
guild inbox --since-last
guild statusline --session <id> [--ctx <pct>]

guild hook session-start   # reads Claude Code hook JSON on stdin
guild hook prompt-submit
guild hook post-tool-use
guild hook pre-push

guild seed <file.json>
guild rebuild
guild export --visibility guild
```

Refs use two literal formats: `pr:<owner/repo>#<n>` and `task:<quest>/<tid>`.
Durations: `30m`, `8h`, `3d` — anything else is rejected.

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
5. Nothing actionable: the exact blockers (pending deps and who says so, open
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

### Task done resolver

`guild next`'s dependency check (and future `guild drift`) resolve whether a
task is done by asking, in this fixed precedence order, the first source
that has an opinion: **guild** (any `quest_tasks` row for that epic/tid —
`done` state means done, any other state means not done), **tracker** (JIRA,
phase 3 — no opinion yet), **sdd** (`tasks.sdd_status`). No opinion anywhere
→ not done, never assumed done. When more than one source has an opinion and
they disagree, the disagreement is returned and surfaced by `guild next`.

### `guild handoff` and resuming a party

`guild handoff --in-flight "..." --learned "..."` (both required, non-empty)
renders `$XDG_DATA_HOME/guild/handoffs/<party>-g<N>.md` from the DB (active
quests, the full `guild next --all` queue, PRs, open asks, active notices and
claims, plus the two free-text fields), records `party.handed_off` (party →
`awaiting-leader`, `leaders.handoff_path` set for this generation) and prints
one command for the human to run:

```
claude -n <party>-g<N+1> "run in Bash `guild party resume <party>`, then read the handoff it prints"
```

There is no `/guild-resume` skill: the printed prompt is the entire contract.
`guild party resume <party>` prints the previous generation's handoff content
plus a single (read-only, non-acknowledging) `guild next` line. A
freshly-resumed generation's very next `SessionStart` (e.g. after `/clear`)
shows the same handoff + next line once more, then reverts to the normal
brief.

`guild party resume <party> --session <name>` lets a human resume a party for
a session that already exists but was never bound (resolves the session id
via `~/.claude/sessions` by its `/rename` name). It is refused from inside a
Claude Code session (use the plain form there) and fails clearly when the
name is not found.

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
allowed only for `answer`, `dismiss`, `notice create`, `notice close`, and
all reads.

A project is resolved from the current working directory against every
project config's `paths` globs (first match wins, configs read in filename
order). Commands that need a project fail clearly when none matches.

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
    "order_list": "^\\d+\\.\\s+(.+)$"
  },
  "next": {"stale_hours": 8},
  "handoff_threshold": 80
}
```

- `sdd` (optional): drives `guild sync --source sdd`. Three independent,
  explicit regexes (`task_heading`, `key_ref`, `deps_line`, `status_line`) plus
  an optional `order_list`; no hidden defaults, no fallback shape. A
  `tasks.md` file with zero `task_heading` matches is reported unparseable
  and skipped; other files still sync; `guild sync` exits non-zero if any
  file failed. See "SDD parsing rules" below for exactly how each regex is
  used.
- `next.stale_hours` (optional): threshold for `guild next` tier 3
  (`converging` PR with no activity). Absent → that tier is skipped, never
  defaulted.
- `handoff_threshold` (optional): context-usage percent (0-100) at or above
  which `UserPromptSubmit`/`PostToolUse` hooks nudge once per session toward
  `guild handoff`. Absent → no nudge.
- Unknown top-level keys are allowed (reserved for phase 3: `jira`).

### SDD parsing rules

- `task_heading` matches a `##`/`###` line; group 1 is the tid, group 2 the
  title. Match lazily up to the **first** spaced dash after the tid (`.*?\s[—–-]\s+`),
  so a `→ KEY` or `(KEY)` connector before it is skipped and hyphens inside the
  title (`cross-tenant`, `(KEY-12)`) are kept.
- `key_ref` is searched (not matched) against the heading line only; a
  generic token pattern such as `[A-Z]{2,10}-\d+` covers `→ KEY`, `(KEY)` and
  `· KEY` connectors. No match on that line → no key, even if the task has a
  `**JIRA:**`-style line elsewhere in its body (out of scope for the heading
  regex by design).
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

## Storage

Append-only `events` table (SQLite, WAL, `busy_timeout=5000`, writes wrapped
in `BEGIN IMMEDIATE`) plus projection tables kept in sync in the same
transaction: `parties`, `leaders`, `quests`, `quest_tasks`, `epics`, `tasks`,
`prs`, `asks`, `notices`, `claims`, `cursors`. `guild rebuild` drops every
projection and replays all events from scratch — the only exception is
`cursors`, which is a per-session read position, not domain state, and is
left untouched by rebuild.

`epics`/`tasks` are observed-only (never written by a guild command): they
hold whatever `guild sync --source sdd` last read, keyed by
`(project, epic)` / `(project, epic, tid)`. `leaders.handoff_path` and the
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
      }
    ]
  }
}
```

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
- `pre-push`: inspects `git push` commands before they run; blocks pushes to
  a branch whose only PRs are merged/closed.

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

The JIRA adapter, `observations`, `drift` and `raid` are phase 3.

**Idle-session wake: no-go (spike, this release).** The design considered
having a resumed leader auto-spawn (`claude -n ...`) instead of asking a
human to run one command. Not built: the mechanism that could plausibly wake
or drive a specific Claude Code session from the outside is the per-session
socket under `~/.claude/`, which is undocumented internal IPC with a
per-session private key — not a public contract. Building against it now
would mean guild's core handoff flow depends on an implementation detail
that can change without notice. `guild handoff` instead prints the one
`claude -n <party>-g<N+1> "..."` command for a human (or an orchestrating
agent) to run; revisit auto-spawn if a public, documented session-control
contract appears.
