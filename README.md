# agents-guild

Guild is a local command line tool that coordinates several Claude Code sessions working in parallel on the same codebase, or on several codebases. It gives them one shared board, a queue of decisions that wait for a human, PR tracking, claims on shared areas, a merge order and a local web board. It is for developers who run more than one Claude Code session at a time and want them to stop stepping on each other.

> **Built with AI. Use at your own risk.**
> This project was developed with AI coding agents (Claude Code), with human direction and review. It is provided as-is, without warranty of any kind (see [LICENSE](LICENSE)). Guild installs hooks and permission rules into your Claude Code settings and can launch sessions on its own: read what [install](#install) changes before running it, and keep backups of anything you care about.

## The Guild

In the old days every coder walked alone. Each session woke with no memory, worked until its lantern ran dry, and vanished, leaving half-merged branches and unanswered questions in the dark.

Then the Guild was founded.

The Guild keeps the **ledger**: one book, kept by code, where nothing is written from memory. Work arrives as **quests**, broken into **tasks**. Sessions band into **parties** that outlive any single member: when a session's lantern burns low, it writes a **handoff**, and the next **generation** takes up the same quest without losing a step. Those who come for a single job are **adventurers**: one task, one PR, a report, and gone.

On the **notice board**, sessions warn each other: the pipeline is down, the fix is PR #877. Before entering contested ground, a CI workflow or a shared config, a party plants a **claim**, and the others route around it. When a danger is too big for one party, parties join a **raid**.

But the Guild has a master: you. No party decides what only a human may decide. Those questions go into the **asks** and wait for your word. Nothing merges unless your hand merges it; the **merge queue** only tells you which comes first.

While the parties rest, **health adventurers** and **solo players** walk the walls. They mend a broken main, tend the dependency bumps, and call you only when it matters. Guilds in distant lands may join a **realm** and trade word across machines.

And the Guild keeps its own counsel. No trace of it leaves your machine: your PRs, commits and cards look like anyone else's.

| Lore | What it really is | Command |
| --- | --- | --- |
| Ledger | Local SQLite state, written only by code | `guild board`, `guild whoami` |
| Quest, task | Units of work: a quest holds tasks | `guild quest`, `guild task` |
| Party | A durable line of work that outlives any one session | `guild party` |
| Handoff, generation | A fresh session takes over when context runs low | `guild handoff`, `guild revive` |
| Adventurer | A session that does one job and reports | `guild adventurer`, `guild adventurers` |
| Notice board | Messages between sessions | `guild notice`, `guild notices` |
| Claim | A lock on a shared area or task | `guild claim`, `guild claims` |
| Raid | Several parties on one shared concern | `guild raid`, `guild raids` |
| Asks | Decisions only the human can make | `guild ask`, `guild asks`, `guild answer` |
| Merge queue | The order to merge PRs by hand | `guild merge-queue`, `guild review-md` |
| Health adventurers, solo players | Background jobs that fix main and bump dependencies | `guild adventurer launch`, `guild solo` |
| Realm | Guilds on several machines sharing status | `guild realm` |

## Requirements

- Linux. It is the only tested platform.
- Python 3.10 or newer. Guild uses only the standard library.
- [Claude Code](https://claude.com/claude-code).
- `git`.
- `gh`, authenticated: guild reads PR state through it.
- `tmux`, only for the commands that open sessions in a window: `guild revive`, `guild adventurer launch`, `guild solo launch` and `guild handoff --respawn`. Everything else works without it.

## Install

Use at your own risk: see the disclaimer above.

1. Clone the repo: `git clone <repo-url> agents-guild`.
2. Keep that clone on `main` and never edit it. Hooks run `guild` from it in every session, so a half-written change would go live at once.
3. Run `./install.sh` from the clone.
4. Add this line to `~/.claude/CLAUDE.md`:
   ```
   @~/.claude/GUILD.md
   ```
5. Make sure `~/.local/bin` is on your `PATH`.
6. Name your guild in `~/.config/guild/guild.json`: `{"name": "<your-guild>"}`. Without it `guild doctor` warns and suggests a name.
7. Run `guild doctor`. It checks, read-only, that hooks, permission rules, `GUILD.md` and project configs are in place, and exits 1 naming what is missing.

Run `guild --help` for every command, and `guild <command> --help` for its subcommands and flags.

### What install changes on your machine

- Symlinks `~/.local/bin/guild` to `bin/guild` and `~/.claude/GUILD.md` to `GUILD.md`. An existing file at either place is left alone with a warning.
- Merges guild hooks and permission rules into `~/.claude/settings.json`. It adds only what is missing, keeps every other entry and copies the previous file to `settings.json.bak`. It refuses, leaving the file untouched, when the file is not valid JSON.
- Keeps data, config and state under the XDG directories (see Uninstall).

The details are in [Install](docs/install.md).

## Update

Run from the base clone:

```
./update.sh
```

Check what you run with `guild --version`.

It refuses if the clone has local changes or is not on `main`. Otherwise it fast-forwards to `origin/main`, lists the new commits, re-runs `install.sh` and runs `guild doctor`. It never edits project configs.

## Uninstall

```
./uninstall.sh [--purge]
```

It removes the hooks and permission rules from `~/.claude/settings.json` and the two symlinks. It keeps your data unless you pass `--purge`, which deletes these three directories:

- `~/.local/share/guild`: the database, handoffs and party memory.
- `~/.config/guild`: global and project config.
- `~/.local/state/guild`: markers and locks.

Then remove by hand the `@~/.claude/GUILD.md` line from `~/.claude/CLAUDE.md`.

## First 10 minutes

1. Register a project. Guild finds a project by its path. Save this as `acme.json`, with your own name, paths and repos:

   ```json
   {
     "name": "acme",
     "paths": ["~/code/acme/*"],
     "github": {"repos": ["acme/app"]}
   }
   ```

   Then run `guild init-project acme --config acme.json`. The file lands in `~/.config/guild/projects/acme.json`. See [Configuration](docs/configuration.md) for every key.
2. Run `guild doctor` again. It loads every project config and tells you if one is broken.
3. Open Claude Code inside a checkout that matches the project paths. The hook tells the session it is not bound and suggests how. For several PRs it starts a party: `guild party start <name> --reason "<why>" --goal "<what for>" --done-when "<end condition>"`. For one PR it starts an adventurer: `guild adventurer start "<job>" --task <quest>/<tid> --reason "<why>"`. Ask the session to follow it.
4. See the board: `guild board`. It shows each party, its tasks, its PRs and what it waits on.
5. See what needs you: `guild asks`. Answer with `guild answer <id> "<text>"`, or dismiss with `guild dismiss <id>`, from your own terminal.
6. Open the web board: `guild web`. It serves the same data in your browser and lets you act on it.
7. Ask what to do next: `guild next` prints the next action for your party.

## Core concepts

- **Party**: a named line of work. Sessions come and go, the party stays. When a session's context runs low it hands off and a fresh one continues.
- **Quest and task**: a quest is a goal, a task is one step of it. Tasks can come from an SDD epic or be added by hand.
- **Adventurer**: a session that does one job, opens one PR, reports and ends.
- **Ask**: a decision a session cannot make. It waits in `guild asks` until you answer.
- **Notice and claim**: a notice is a broadcast between sessions. A claim reserves a shared area, such as a CI workflow, so two sessions do not edit it at once.

More in [Concepts](docs/concepts.md).

## Daily commands

```
guild board                       # what every party is doing
guild board --party <name>        # only one party
guild next                        # the next action for your party
guild asks                        # open decisions waiting for you
guild asks <id>                   # one ask in detail
guild answer <id> "<text>"        # answer an ask, from your own terminal
guild notices                     # notices addressed to you
guild claims                      # active claims
guild adventurers                 # one-job sessions and their state
guild merge-queue                 # the order to merge PRs by hand
guild merge-queue --head          # only the PR to merge now
guild review-md                   # PRs ready for you, as markdown
guild sync --source gh            # refresh PR state from GitHub
guild revive --list               # commands to relaunch parties after a reboot
guild ideas                       # parked ideas
guild history                     # quests, raids and totals over time
guild web                         # the local board in a browser
guild doctor                      # check the install
```

Every command and flag is in [Commands](docs/commands.md).

## Privacy

Guild is local and optional. Nothing of it shows in PRs, commits or cards, so a teammate who does not use guild finds no trace of it. `guild doctor --scan-prs` checks open PRs for leaks.

## Contributing

This repo is shared as-is. No issues or pull requests are accepted. To read how guild is built and tested, and its specs in [`sdd/`](sdd/README.md), see [Development](docs/development.md).

## Documentation

- [Install](docs/install.md): Install, update and uninstall in detail
- [Concepts](docs/concepts.md): Glossary, identity and the quest board
- [Commands](docs/commands.md): Every command and flag
- [Configuration](docs/configuration.md): Global and project config
- [Hooks](docs/hooks.md): Hooks and the agent rules
- [Data](docs/data.md): Storage, personal data caps and the seed schema
- [Realms](docs/realms.md): Sharing state between machines
- [Development](docs/development.md): Developing guild and project status
