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
guild party resume <party>
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

guild claim <area> --ttl <dur>
guild release <area>
guild claims

guild board [--party <name>]
guild sync --source gh
guild brief
guild inbox --since-last
guild statusline --session <id>

guild hook session-start   # reads Claude Code hook JSON on stdin
guild hook prompt-submit
guild hook pre-push

guild seed <file.json>
guild rebuild
guild export --visibility guild
```

Refs use two literal formats: `pr:<owner/repo>#<n>` and `task:<quest>/<tid>`.
Durations: `30m`, `8h`, `3d` — anything else is rejected.

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
  "github": {"repos": ["acme/app", "acme/docs"]}
}
```

Unknown top-level keys are allowed (reserved for phase 2/3: `jira`, `sdd`).

## Storage

Append-only `events` table (SQLite, WAL, `busy_timeout=5000`, writes wrapped
in `BEGIN IMMEDIATE`) plus projection tables kept in sync in the same
transaction: `parties`, `leaders`, `quests`, `quest_tasks`, `prs`, `asks`,
`notices`, `claims`, `cursors`. `guild rebuild` drops every projection and
replays all events from scratch — the only exception is `cursors`, which is
a per-session read position, not domain state, and is left untouched by
rebuild.

Default paths (all overridable via env, useful for tests):

- DB: `$XDG_DATA_HOME/guild/guild.db` (default `~/.local/share/guild/`).
- Config: `$XDG_CONFIG_HOME/guild/` (default `~/.config/guild/`).
- State: `$XDG_STATE_HOME/guild/` (default `~/.local/state/guild/`).
- Claude sessions: `$GUILD_CLAUDE_SESSIONS_DIR` (default `~/.claude/sessions`).

## Seed schema

`guild seed <file.json>` loads state through the normal event path (so
`guild rebuild` reproduces it). Seeded PRs skip the `gh` existence check
(payload flag `seeded: true`).

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

`GUILD.md` holds the instructions agents need to use guild (bind, track PRs, ask, notice, claim). `install.sh` links it to `~/.claude/GUILD.md`; add one line to `~/.claude/CLAUDE.md` so every session loads it:

```
@GUILD.md
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
  spawns `guild sync --source gh` in the background, detached.
- `prompt-submit`: prints only events new since this session's cursor
  (notices, answers/dismissals of this party's asks). Unbound sessions also
  get the binding hint, once. Local DB only, no network.
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

Phase 1 (core) only: identity, party/quest/task/pr/ask/notice/claim, board,
brief, inbox, statusline, `gh` sync, pre-push guard, hooks, seed/rebuild/
export. `guild next`, `guild handoff`, the SDD/JIRA adapters, `drift` and
`raid` are later phases.
