# Configuration

Back to the [README](../README.md).

## Global config

`$XDG_CONFIG_HOME/guild/guild.json` (default `~/.config/guild/guild.json`),
optional, written by hand:

```json
{"name": "forge", "handoff_margin": 10, "resource_retention_days": 90}
```

- `name` (slug, optional): the name of this guild. It is the name a realm hub knows
  the guild by, so `guild realm join` needs it, and the web board shows it in the
  header. `guild doctor` warns while it is missing and suggests the host name.

- `handoff_margin` (integer 0-100): when set and an automatic compaction has
  been recorded, the handoff threshold of every project is the last compaction
  percentage minus this share of it (85% with a margin of 10 gives 76%, rounded
  down), instead of `handoff_threshold`. The margin is a share, not points, because
  with a 1M context window Claude Code may compact at around 21% of it.
  It is global because the compaction point comes from the user's Claude Code
  settings. The last compaction wins over older ones, so after a change to
  those settings one compaction corrects it: until then a lower old point
  hands off early, and a higher old one is caught by the nudge that follows
  every compaction.

- `resource_retention_days` (positive integer, at most 3650, absent: 90):
  age in days past which `guild compact` deletes resource samples.

Whatever the source, a session's threshold is never below its starting
percentage plus 5 (the first nonzero `guild statusline --ctx` reading, kept in
`$XDG_STATE_HOME/guild/ctx-baseline`): a fresh session that already starts
above the threshold would otherwise hand off at once, and every respawned
generation after it too.

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
  "handoff_threshold": 40,
  "lifecycle": {
    "on_pr_merged": {"command": ["scripts/cleanup-merged.sh", "--dry-run"], "timeout_minutes": 30},
    "on_pr_closed": {"command": ["scripts/cleanup-merged.sh"], "timeout_minutes": 30}
  },
  "health_jobs": [
    {"name": "red-main", "command": "/check-main", "every": "1d"},
    {"name": "drift", "command": "/check-drift", "every": "3d"}
  ],
  "solo_players": [
    {"repo": "acme/app", "job": "red-main", "name": "mender"},
    {"repo": "acme/app", "job": "dependabot"}
  ]
}
```

`sdd.root` above can instead be `"git_repo": "~/Documents/_projects/acme/sdd-docs", "git_ref": "origin/main"` to read the same `epics_dir` from a git ref instead of a working copy.

`epics_dir` may be a subfolder (e.g. `"epics_dir": "docs/specs/epics"`), and `git_repo` may be the project's code repo itself: only `<epics_dir>/<epic>/tasks.md` files are read, in both `root` and `git_repo` modes.

All keys. The loader rejects a wrong type with a clear error for every key except `sdd`, `handoff_threshold` and `pii_patterns`, which are read where they are used. An optional key is off when absent; the only default is the one stated below (`handoff_threshold`). Unknown top-level keys are allowed.

- `name` (string, required): project name, a valid slug; `guild init-project <name>` requires it to match, and the file is `<name>.json`.
- `paths` (non-empty list of globs, required): checkouts of the project; `~` is expanded. The project of a command is the first config with a glob matching the cwd or one of its ancestors.
- `github` (object, required): `repos`, a list of `owner/repo` the project tracks.
- `sdd` (object, absent: no SDD sync): drives `guild sync --source sdd`. Explicit regexes `task_heading`, `key_ref`, `deps_line` and `status_line`, plus optional `order_list` and `key_line`; no hidden defaults, no fallback shape. A `tasks.md` with zero `task_heading` matches is reported unparseable and skipped, and one that repeats a task id is reported as `duplicate task ids: <tids>` and skipped; other files still sync; `guild sync` exits non-zero if any file failed. See "SDD parsing rules".
  - Exactly one way to read `epics_dir`:
    - `root`: a plain checkout path. `guild` reads `tasks.md` files straight off disk, so the checkout must exist and stay put.
    - `git_repo` + `git_ref` (e.g. `"origin/main"`), both required together: `guild` runs `git -C <git_repo> fetch --quiet origin`, lists `tasks.md` files at `<git_ref>` with `git ls-tree` and reads each with `git show <git_ref>:<path>`. It never checks out, resets or otherwise touches `git_repo`'s working tree, so it is safe to point at a clone a human or another session is using. A failed fetch, an unknown ref, or zero `tasks.md` files under `epics_dir` at that ref is a clear error, never an empty sync. `epics.sdd_path` is stored as `git:<git_ref>:<path>` in this mode. `root` reads whatever the checkout holds, so a checkout that lags origin or carries another session's edits yields stale SDD state and false disagreements. Prefer `git_repo` + `git_ref` (e.g. `origin/main`) for a docs repo shared with other sessions: a worktree can be deleted or switched out from under `root`, and `sync` would silently read nothing.
  - `epic_key_field` (string, absent: `epics.jira_key` is `NULL`): the frontmatter key (a `key: value` line between the leading `---` markers of the epic's `tasks.md`) that names the epic's own tracker card, e.g. `jira: DEMO-1`. Never guessed from the epic slug.
  - `epic_status_field` (string, absent: `epics.sdd_status` is `NULL`): the frontmatter key that carries the epic's own SDD status, e.g. `status: done`, parsed like `epic_key_field`.
- `tracker` (object, absent: no tracker sync): drives `guild sync --source tracker` (see "Tracker sync"). `kind` is required when the block exists; only `"jira-acli"` is supported, anything else is rejected when the config loads.
  - `browse_url` (string starting with `https://`, absent: tasks carry no `card_url`): the base `guild web` prepends to a task's tracker key to build its card link (`https://acme.atlassian.net/browse/DEMO-1`).
- `next.stale_hours` (positive integer, absent: `guild next` skips its stale-`converging` step and the web in-progress page shows no stale marker): hours without activity after which a `converging` PR is reported and a quest is marked stale.
- `handoff_threshold` (integer percent 0-100, default 80): context usage at or above which the `UserPromptSubmit`/`PostToolUse` hooks nudge once per session toward `guild handoff` (`guild handoff --respawn` for sessions in a window guild launched; the same nudge comes right after a compaction, whatever the percentage) and the board reports the party as context high. The nudge asks the session to start nothing new, let running executions finish, hand off and stop. Recommended: 40, so sessions stay short and each fresh generation starts from the brief. A global `handoff_margin` replaces it with the last compaction minus the margin (see "Global config"). Claude Code's `autoCompactWindow` setting (tokens) and `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` env var move that point; for example `autoCompactWindow: 1000000` with an override of `85` and a threshold of `70`.
- `max_open_prs_per_party` (positive integer, absent: no cap): open tracked PRs of one party at which `guild next` offers no new task and says to merge the first PR in queue order. Recommended: 3.
- `max_open_prs` (positive integer, absent: no cap): the same, counting the open tracked PRs of all parties of the project. Size it to review throughput, e.g. 10.
- `max_open_prs_per_file` (positive integer, absent: no warning, no extra calls): when a `git push` diff touches a file that this many other open tracked PRs of the project already change, `pre-push` warns (never denies) naming the file and those PRs. Needs `guild sync --source gh`, which then stores the changed files of every open tracked PR (`pr_files`, one `gh pr view` call per PR). Exclusive `area:` claims stay for files that need exclusivity.
- `finding_guard_threshold` (positive integer, absent: findings are recorded silently): when `guild finding record` has counted that many distinct PRs for one finding class, one notice to `project:<name>` asks to make the class an architecture guard.
- `human_ready.ci_label` (non-empty string, absent: no label tracking): the label that makes the project run CI. `guild sync --source gh` stores per PR whether it carries the label (`prs.ci_label`) and how many comments or reviews by other authors came after the head commit (`prs.comments_after_head`). It also stores `prs.checks_billing` for PRs with failing checks (see Main blocked by billing). `guild pr ready-check` and the web queue read these stored facts: a comment or review after the head makes the PR not ready, and a PR without checks whose label is absent is `ready (CI pending)` and names the label.
- `human_ready.notice_comments` (list of `{"author": "<login>", "text": "<literal>"}`, absent: every entry counts): comments and reviews that review nothing, such as budget or trial notices of a bot. An entry is notice-only when its author equals `author` AND its body contains `text`, both compared case-insensitively; a review body can be empty. Both values are non-empty strings and no other key is allowed. It applies to comments and reviews. Only `guild pr wait` reads it: notice-only entries do not wake it, while human-ready (`comments_after_head`) is unchanged. Example: `{"author": "notifier", "text": "Usage notice"}`. Stored per PR as `prs.other_author_comments`.
- `human_ready.trace_validator` (object, absent: no trace check): `{"command": [<argv>...], "timeout_seconds": N}` with `command` a non-empty list of non-empty strings and `timeout_seconds` an integer from 1 to 300. For each `ready` tracked PR, `guild sync --source gh` runs it as argv without a shell, from the main checkout of the PR's repo, in its own process group that is killed at the timeout. `{head_sha}` (hex), `{pr}` (integer) and `{comments_file}` (a 0600 temporary JSON shaped like `gh pr view --json comments,reviews`, deleted after the run) are replaced inside the elements. Exit 0 means the trace is valid; any other exit means invalid, with the last line of the output as reason (200 characters, control sequences stripped, withheld when it matches the personal-data, secret or instruction screen). A timeout, a launch error or a missing clone leaves the trace not validated, never valid. The result is stored as `prs.trace_valid` and `prs.trace_reason` in the sync record, which `guild export` includes: print only a short reason. The validator must be side-effect free and idempotent. Trust boundary: the validator inherits guild's full environment, including any tokens, so write it as a script you trust and keep it free of side effects. A repo-relative command runs from the main checkout, which may be on a branch whose files the PR changed, so prefer an absolute path to a reviewed script. The check runs for every `ready` tracked PR on every sync, one after another, each up to its timeout. The stored result is as fresh as the last sync: right after the key is added or a PR becomes Ready, the PR counts as having no trace result until the next sync. `guild pr ready-check` and the web queue read the stored result and never run the command.
- `handoff_retention_days` (positive integer, at most 3650, absent: kept forever): days after a party closes at which `guild handoff prune` deletes its last handoff file.
- `pii_patterns` (list of regexes, absent: only the built-in email pattern): checked against notice text, ask question/context, answer text and handoff `--in-flight`/`--learned` for the caller's project. A match rejects the command with an error that names the field, never the matched text.
- `notify` (object, absent: nothing is run): `{"command": [<argv>...]}`, a non-empty list of non-empty strings run once per blocking wait (see "Session status"). `command` is the only allowed key.
- `shared_areas` (list of globs relative to the repo root, absent: no guard): e.g. `config/routes.rb`, `db/migrate/*`; matched with `fnmatch` against POSIX-style relative paths by `guild hook pre-edit`, `pre-commit` and `pre-push` (see "Hooks"). Present: `shared_area_claim_ttl` is required or the config fails to load.
- `shared_area_claim_ttl` (duration `30m`/`8h`/`3d`, required with `shared_areas`): the TTL the guards claim a matched area for.
- `migration_paths` (list of globs, absent: the migration clash check is skipped and no extra `gh` call is made): matched with `fnmatch` against changed file paths, e.g. `db/migrate/*`. See "Migration version clash" under `sync`.
- `fast_forward_base` (boolean, absent or `false`: no clone is ever modified): `true` makes `sync --source gh` fast-forward the local base branch of merged repos (see "Base fast-forward" under [`guild sync`](commands.md#guild-sync)).
- `health_jobs` (list of `{"name", "command", "every"}`, absent: no jobs): recurring jobs that keep the project healthy (see [Health jobs](commands.md#health-jobs)). `name` is a unique slug, `command` a non-empty string that does not start with `-`, the prompt or skill the job's session runs first, and `every` a duration like `30m`, `12h` or `3d`. Any other shape fails to load with an error naming `health_jobs`.
- `solo_players` (list of `{"repo", "job", "name", "class", "command", "trigger"}`, absent: none): per-repo solo players (see [Solo players](commands.md#solo-players)). `repo` is one of `github.repos`, each `(repo, job)` pair appears once, `name` and `class` are optional non-empty labels on built-in jobs (`red-main`, `dependabot`, which refuse `command` and `trigger`), and any other `job` is a custom player that requires `command`, `trigger` (`main-red`, `dependabot` or `every <duration>` of at least 1h) and `class`. Any other shape fails to load with an error naming `solo_players`.
- `lifecycle` (object, absent: no command ever runs): commands run on PR lifecycle events (see [Lifecycle commands](commands.md#lifecycle-commands)). Keys are `on_pr_merged` and `on_pr_closed`, any other key fails to load. Each value has exactly `command` (non-empty list of non-empty strings, never a shell string) and `timeout_minutes` (integer from 1 to 1440, required).

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
