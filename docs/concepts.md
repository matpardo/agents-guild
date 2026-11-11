# Concepts

Back to the [README](../README.md).

The words guild uses, how it knows who is acting, and how work is planned before anyone starts it.

- [Glossary](#glossary)
- [Identity](#identity)
- [Quest board](#quest-board)

## Glossary

- **guild** — one install: the database and config on this machine (or
  person).
- **party** — a durable work lineage that survives session handoffs. Session
  names change; the party does not. Owns quests, PRs and claims.
- **adventurer** — one session doing one job on one project: a synced SDD
  task or a one-off repo change. No generations, no handoff; it ends with `guild
  adventurer done --pending`. Never owns a quest.
- **leader** — the live session of a party: zero or one. An attribute of
  `party`, not a command of its own.
- **generation** — one session of a party; a handoff or `guild revive` starts
  the next.
- **quest** — a party's current assignment: a slice of an epic, a whole epic,
  or a stream with no epic at all (e.g. "fix CI costs"). Owned by zero or one
  party; a quest no party owns is an open quest.
- **epic** — a planning unit owned by external docs/trackers; guild reads it
  and never writes to it.
- **task** — a step of an epic, or a step of a no-epic quest. Guild tracks
  its work state (queued/active/blocked/done), not its plan.
- **raid** — a named channel several parties join for a shared concern (e.g.
  CI), so a notice can reach exactly that audience. Exists while it has at
  least one active (non-expired) member; join/leave with `guild raid
  join|leave`, post to it with `guild notice create ... --to raid:<name>`.
- **brief** — what a fresh session reads: handoff, task, PR and asks.

## Identity

Guild finds out who is acting from the session, not from a login.

**Actor resolution.** `CLAUDE_CODE_SESSION_ID` (or, for hooks, the `session_id` field on stdin) → `leaders` table → party.

- An unbound session cannot write. It is refused with a hint to run `guild party start <name> --reason "<why>" --goal "<goal>" --done-when "<condition>"`, `guild adventurer start "<job>" --task <epic>/<tid> --reason "<why>"` or `guild party resume <party>`. Reads always work.
- No session id at all (a plain terminal) resolves to the actor `human`. It is allowed for `answer`, `dismiss`, `notice create|close|seen|unseen`, `merge-queue pin|unpin`, `main red|green`, `finding record`, the PR block and unblock buttons of `guild web`, and all reads. Commands that write a party's own work (`task`, `pr track|set`, `claim`, `raid`, `ask`, `handoff`, `quest`) refuse it.

**Project resolution.** A project is resolved from the current working directory against every project config's `paths` globs (first match wins, configs read in filename order). Commands that need a project fail clearly when none matches.

**Trust model.** Guild is single-user, same-OS-user software. Hook stdin (the `session_id`, `cwd` and `tool_input` JSON Claude Code writes) and the `CLAUDE_CODE_SESSION_ID` environment variable are trusted at face value, by design. Anything that can set that env var or write to that stdin already runs as the same local user as guild itself, so there is no privilege boundary to enforce between local processes. Guild is not a sandbox and does not attempt to be one.

**Names.** Party, quest and project names are validated against a slug rule (`^[A-Za-z0-9][A-Za-z0-9._-]*$`, no `..` anywhere) before they can become a filesystem path (handoff files, project config files). This is defense against path traversal, not an identity boundary. A party name is never reused: `party start` and `adventurer promote` refuse a name that any party ever had, closed parties included, so a name always means one party and its history (tasks per day, leaders, events).

## Quest board

Plan work before any party exists. `guild quest add <slug> --open ...` creates a quest with no party, from the human's terminal, a party or an adventurer. It runs the same checks as a plain `quest add`: the epic and tasks must be synced, and a task another quest, claim or adventurer holds is refused. A task inside an open quest counts as taken for every other quest, `task add` and claim.

### Commands

- `guild quest board [--project <name>]` lists the open quests and, per synced epic in SDD order (done and archived epics skipped), the tasks no quest covers, no claim holds, no adventurer holds and SDD does not mark done.
- `guild quest take <slug>` gives an open quest of the session's project to its party. A task an adventurer holds stays with the adventurer: `guild next` skips it and `task start` refuses it until `adventurer done`.
- `guild quest release <slug>` returns the quest to the board. The owner only, and only while every task is queued with no open PR and no claim.
- `guild board` prints a `QUEST BOARD` block per such project: each open quest with its task count and dates and the number of free tasks per epic.

### Who left a quest

A quest remembers who left it: the party or adventurer that ran `quest add --open`, or the party that released it (nothing when the human created it). Quests created before this existed have no author.

- `guild quest board` and the web quest board print `left by <name>` on each open quest, so parked follow-ups stay visible after the party closes.
- The party block of `guild board` and of the web board lists what the party left, as `left: <slug> — <title> (no party yet | taken by <party> | done)`. The final report uses the same list.

### What `guild next` says

- A party that has a quest, no unfinished task in its quests and no open tracked PR gets `own work done: check done-when "<text>", then guild party close or report to the dev` (without the `check done-when` part when the party has none).
- `guild next` never offers an open quest: it could belong to the work of another active party.
- `guild next --all` also lists every open quest of the project, oldest first, for information only, as `open quest <slug> — <title> (left by <name>)` (`no author` when none). `guild quest take` runs only when the human points at a quest.
- A party with a blocked task still gets `nothing actionable` plus the blocked lines, and so does a party with no quest yet.

### Adventurer tasks

An adventurer always starts on a task (`adventurer start --task`, required except for health jobs). The task is one of:

- A synced SDD task `<epic>/<tid>`.
- A new task the PR adds to an epic already synced (`guild drift` reports `adventurer task not in SDD` if it is still missing after the PR merged).
- `<quest>/<tid>` of a no-epic open quest (`guild quest add <slug> --open --no-epic --tasks T01 --titles "..."` when the project has no SDD).

`adventurer done` marks that task done and closes the quest with its last task; the final report then prints `quest <slug> done`.

### Dates

Quests and quest tasks show when they were created and, if they changed later, when they last changed, as `created 2026-10-24 09:15 · updated 2026-10-24 11:02` (local time, minute precision; just `created …` while nothing changed). The label appears on open quests, on the quests and tasks of a party in `guild board` and in the web (`dates` in the quest and task models, `null` when unknown).

- A quest changes when it is taken, released, done or closed with its party, or when a task is added or moved.
- A task changes when it starts, blocks, finishes or moves.

The same label appears on:

- Tracked PRs: tracked, then last activity (a change of lifecycle, waits, flags or synced state, not a sync with nothing new).
- Claims, in `guild claims` and the claims line of a party: claimed, then last renewal.
- Each party: first leader start, then last handoff, resume or close.
- Asks: created, then answered, in `guild asks`, `guild asks --all`, `--answered` and the web, replacing the old `answered:` line.
- Adventurers: started, then done, in `guild board` and the web. `guild adventurers <id>` prints started and done in local time.

The web model carries it as `dates` in the PR, claim, party, ask and adventurer entries (`null` when unknown). The party `started` key, the `started` key of the adventurer model and the `answered` key of the answered-ask model are replaced by `dates`.

### Web quest board

The web board has a `quest board` section for every registered project with synced epics or open quests, even with no party (`quest_boards` in `/api/board`: `name`, `open_quests`, `free_tasks` per epic and the active `parties` of the project).

- Each open quest lists its tasks (an adventurer-held task is marked) with a party select and `Assign`.
- Each epic with free tasks has a checkbox per task, a slug, a title and `Create open quest`.
- A party card shows `Release` on a quest whose tasks are all queued with no open PR or claim (`releasable` in the quest model).

The routes call the same functions as the CLI:

- `POST /api/quests/create-open` (body `{"project", "slug", "title", "epic", "tasks": ["T01", ...]}`)
- `POST /api/quests/<slug>/take` (body `{"party"}`)
- `POST /api/quests/<slug>/release` (body `{}`)

A refusal answers `422` with the message, a wrong type `400`.
