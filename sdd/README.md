# agents-guild specs (SDD)

Spec-driven development for agents-guild itself. Every change starts here as an epic; tasks are marked done in the same PR that implements them, so specs and code never travel in separate repos.

## Layout

```
sdd/
  epics/<slug>/spec.md       what and why (required)
  epics/<slug>/tasks.md      executable plan (required from `active`)
  epics/<slug>/discovery.md  open questions and alternatives (optional)
  decisions/YYYYMMDD_<slug>.md  decisions with global impact (ADR)
  _templates/                starting points for each document
```

## Frontmatter

Every document under `epics/` starts with a YAML frontmatter block. It is the single source of truth for name, status, owner and dates; do not repeat them in the body.

| Document | Required keys |
|---|---|
| `spec.md` | `epic`, `type`, `title`, `status`, `owner`, `created`, `updated` |
| `tasks.md`, `discovery.md` | `epic`, `type`, `title`, `status`, `updated` |

- `epic` equals the directory name; `type` equals the file name (`spec`, `tasks`, `discovery`).
- `tasks.md` and `discovery.md` inherit `status` and `title` from their `spec.md`.
- `updated` >= `created`. Update `updated` whenever you edit a document.
- `status`: `draft` (registered, not prioritized) | `active` | `done` | `archived`.

`tests/test_sdd_docs.py` enforces these rules and checks that every `tasks.md` parses with guild's own SDD adapter, so a broken spec fails the test suite like broken code.

## Tasks

Each task is a heading plus two fields, which is the shape guild reads (`guild sync --source sdd`):

```
## T01 — Short title

**Depends on:** —
**Status:** [ ] pending

**What:** one or two lines.
```

- Zero-padded ids: T01, T02… Suffixes are allowed (T03b).
- `**Depends on:**` lists task ids of the same epic, or `—`.
- Only the checkbox counts: `[x]` is done, anything else is pending. Add the PR after it: `[x] done — #12`.
- Mark a task done in the PR that completes it.

## Using it with guild

Register this repo as a guild project; point `sdd.root` at the checkout that follows `main` (the base clone), so a task counts as done once its PR is merged. This stays in `root` mode on purpose: it points at the base clone this project keeps on `main` (see "Install" in the top-level README), not a checkout shared with other sessions. For a docs repo without that guarantee, use `sdd.git_repo`/`sdd.git_ref` instead (see the top-level README's "Project config" section):

```json
{
  "name": "agents-guild",
  "paths": ["~/Documents/_projects/agents-guild", "~/Documents/_projects/agents-guild-dev"],
  "github": {"repos": ["matpardo/agents-guild"]},
  "sdd": {
    "root": "~/Documents/_projects/agents-guild/sdd",
    "epics_dir": "epics",
    "task_heading": "^#{2,3}\\s+(T\\d+\\w*)\\b.*?\\s[—–-]\\s+(.+)$",
    "key_ref": "#\\d+",
    "deps_line": "^\\*\\*Depends on:\\*\\*\\s*(.+)$",
    "status_line": "^\\*\\*Status:\\*\\*\\s*(.+)$"
  }
}
```

## Conventions

- English content; epic slugs in kebab-case describing the goal.
- An epic moves `draft` → `active` when it is prioritized and its `tasks.md` exists; → `done` when every task is done.
- Decisions scoped to one epic go in its `discovery.md` under `## Decisions`; decisions with global impact go in `decisions/`.
