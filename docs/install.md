# Install

Back to the [README](../README.md).

Install, update and uninstall guild, and check that it is wired.

- [Install](#install)
- [Update](#update)
- [`guild doctor`](#guild-doctor)
- [Uninstall](#uninstall)

## Install

```
./install.sh
```

It symlinks `bin/guild` into `~/.local/bin/guild` and `GUILD.md` into `~/.claude/GUILD.md`, then runs `guild wire-settings`, which merges the hooks and permission rules from [Hooks](hooks.md) into `~/.claude/settings.json`. Make sure `~/.local/bin` is on your `PATH`. Nothing in this repo runs it automatically.

First steps: run `guild --help` to see every command with a one-line description, and `guild <command> --help` for its subcommands and flags.

`guild wire-settings` is idempotent and can be re-run at any time:

- It adds only what is missing, keeps every other key and entry as it is, and prints one line per addition (`settings: already wired` when there is nothing to add).
- Before writing it copies the previous file to `settings.json.bak`.
- It refuses, leaving the file untouched, when `settings.json` is not valid JSON.

### Where to install from

Hooks run `guild` in every session, so the installed copy must never be a checkout you are editing: a half-written change goes live at once. Run `./install.sh` from the base clone, keep it on `main` and never edit there.

If you develop guild, do it in a temporary worktree per feature branch, inside the base clone under `.claude/worktrees/` (ignored by git; `main` stays checked out in the base, so a dev worktree never uses it), and remove it after the merge:

```
git worktree add .claude/worktrees/feat-x -b feat/x origin/main
git worktree remove .claude/worktrees/feat-x
```

## Update

After each merge, update the base clone with one command:

```
./update.sh
```

- It refuses if the base clone has local changes or is not on `main`.
- It fast-forwards the clone to `origin/main`, lists the commits it brought, re-runs `install.sh` and runs `guild doctor`.
- It never edits project configs. Through `install.sh` it re-runs `guild wire-settings`, which only adds what is missing and drops retired ask rules.

## `guild doctor`

Read-only checks. It exits 1 and names what is missing when:

- A guild hook is not wired in `~/.claude/settings.json` (including `Notification` and `Stop`).
- `permissions.ask` lacks the `party resume` and `raid join` rules (see [Hooks](hooks.md)).
- `~/.claude/GUILD.md` does not exist.
- A project config does not load, or `guild.json` is invalid.

It prints a `warn` line, never changing the exit code, when:

- The guild state commands are missing from `permissions.allow` (see [Hooks](hooks.md)).
- A session leads more than one active party (`session leads 2 active parties: a, b`).
- A project config still has a `dispatcher` key (ignored, safe to delete).
- A project's `handoff_threshold` is at or above the last compaction (recorded by the `PreCompact` hook), since that threshold never fires. This is the check without a global `handoff_margin`.

With a global `handoff_margin` (see [Global config](configuration.md#global-config)) and a recorded compaction it prints `ok      handoff at 76% (compaction 85% − 10%)`, plus a `warn` when that handoff sits less than 5 points above the starting percentage of the latest session. The handoff would fire on a fresh session, so sessions hand off at that start + 5 instead.

### `--scan-prs`

`guild doctor --scan-prs` additionally lists the open PRs of every project's `github.repos` through `gh` and scans title, body, comments and commit messages with the case-insensitive regex `guild|ask #[0-9]|notice #[0-9]`.

- Each match is a `warn` line naming `repo#n` and where it matched (title, body, comment or commit), never the text.
- Warnings never change the exit code.
- If `gh` fails the scan prints a single `warn` and is skipped.
- It is off by default so `guild doctor` stays fast and offline.

## Uninstall

```
./uninstall.sh [--purge]
```

- It runs `guild unwire-settings`, which removes the hooks and permission rules from [Hooks](hooks.md) in `~/.claude/settings.json`, keeps every other entry, copies the previous file to `settings.json.bak` and prints `settings: nothing wired` when there is nothing to remove.
- It deletes `~/.local/bin/guild` and `~/.claude/GUILD.md` when they are symlinks to this clone. Any other file there is left with a `WARN`.
- The data, config and state directories are kept; `--purge` deletes them.

It does not edit what it cannot own. Remove by hand the line `@~/.claude/GUILD.md` from `~/.claude/CLAUDE.md` and any `guild hook pre-commit` line in `~/.config/husky/init.sh` or in a repository's `.git/hooks/pre-commit`.
