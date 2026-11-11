# Data

Back to the [README](../README.md).

## Storage

Append-only `events` table (SQLite, WAL, `busy_timeout=5000`, writes wrapped
in `BEGIN IMMEDIATE`) plus projection tables kept in sync in the same
transaction: `parties`, `leaders`, `quests`, `quest_tasks`, `epics`, `tasks`,
`prs`, `cards`, `asks`, `notices`, `claims`, `raid_members`, `pr_shared_areas`, `pr_files`,
`merge_queue_pins`, `main_status`, `raid_pauses`, `findings`, `session_status`,
`cost_samples`, `resource_samples`, `resource_machine`,
`leader_windows`, `health_windows`, `cursors`, `transcript_cursors`. `guild rebuild` drops every
projection and replays all events from scratch — the only exceptions are
`cursors` and `transcript_cursors`, which are read positions (per session and
per transcript), not domain state, and are left untouched by rebuild. Events of
the retired dispatcher (`dispatch.*`) replay as no-ops.

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

`quests` and `quest_tasks` also carry `created_at` and `updated_at`, set from
the event timestamps by the same column migration. Rows that exist before the
migration stay empty and show no date until the log is replayed: run `guild
compact`, then `guild rebuild`, with no session working. `guild doctor` warns
`N rows predate stored dates` while any such row remains. The same holds for
`prs.tracked_at`, `claims.created_at` and `claims.updated_at` and
`parties.updated_at`. A claim keeps `created_at` while the same party renews it
and resets it when another party takes the area.

`guild sync --source gh` also stores, per tracked PR, `prs.review_decision`
(`reviewDecision`), `prs.merge_state` (`mergeStateStatus`) and
`prs.base_branch` (`baseRefName`). A `mergeStateStatus` of `UNKNOWN` carries no
signal: the previous `merge_state` is kept. Events recorded before these fields
existed replay with them empty.

For open PRs it also stores `prs.unresolved_threads`, the number of unresolved
review threads (`gh api graphql`, first 100 threads). If that query fails the
failure is reported and the previous count is kept; merged and closed PRs are
not queried.

Default paths (all overridable via env, useful for tests):

- DB: `$XDG_DATA_HOME/guild/guild.db` (default `~/.local/share/guild/`).
- Config: `$XDG_CONFIG_HOME/guild/` (default `~/.config/guild/`).
- State: `$XDG_STATE_HOME/guild/` (default `~/.local/state/guild/`).
- Claude sessions: `$GUILD_CLAUDE_SESSIONS_DIR` (default `~/.claude/sessions`).
- Claude transcripts: `$GUILD_CLAUDE_PROJECTS_DIR` (default `~/.claude/projects`).
- Claude scratchpads: `$GUILD_CLAUDE_SCRATCH_DIR` (default `/tmp/claude-<uid>`).
- Memory: `$XDG_DATA_HOME/guild/memory/<party>/` (default `~/.local/share/guild/`).

`guild` sets `umask 0o077` at CLI entry and explicitly `chmod`s the DB file
(and its `-wal`/`-shm` siblings) to `0600` and the DB, state, handoffs,
projects-config and memory directories to `0700` on every `guild` invocation
— this also repairs a pre-existing world-readable DB from before this
hardening.

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

`guild cost` reads Claude Code transcripts, which hold full conversations. It
parses only `message.usage`, `message.model`, `type`, `timestamp` and
`message.id`; the id and timestamp are used to dedupe and bucket and are not
stored. The stored `cost.sampled` events and `cost_samples` rows hold token
counts, model name, UTC day, session id, party, quest and task, never
conversation text.

`guild resources collect` stores local paths of checkouts and worktrees, branch
names, Docker object names, compose project names and byte counts in
`resources.sampled` events and the `resource_samples` and `resource_machine`
projections. They are local events, never exported, and contain no file
contents, container commands or environment.

A memory item is capped at 500 characters and checked the same way (email,
secret patterns, `pii_patterns`). Unlike the broadcast fields above, memory is
never exported or broadcast: it lives in local files under a party's own
directory, read by that party's later generations and by the local CLI and
web board.

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
      "lifecycle": "draft",
      "needs_ask_answer": true
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
