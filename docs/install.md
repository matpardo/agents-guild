# Install

Back to the [README](../README.md).

## Install, update and uninstall

```
./install.sh
```

Symlinks `bin/guild` into `~/.local/bin/guild` and `GUILD.md` into
`~/.claude/GUILD.md`, then runs `guild wire-settings`, which merges the hooks
and permission rules from "Hooks" into `~/.claude/settings.json`. Make sure
`~/.local/bin` is on your `PATH`. Not run automatically by anything in this
repo.

First steps: run `guild --help` to see every command with a one-line description, and `guild <command> --help` for its subcommands and flags.

`guild wire-settings` is idempotent and can be re-run at any time: it adds
only what is missing, keeps every other key and entry as it is, and prints
one line per addition (`settings: already wired` when there is nothing to
add). Before writing it copies the previous file to `settings.json.bak`. It
refuses, leaving the file untouched, when `settings.json` is not valid JSON.

Hooks run `guild` in every session, so the installed copy must never be a
checkout you are editing: a half-written change goes live at once. Run
`./install.sh` from the base clone, keep it on `main` and never edit there.

If you develop guild, do it in a temporary worktree per feature branch,
inside the base clone under `.claude/worktrees/` (ignored by git; `main` stays
checked out in the base, so a dev worktree never uses it), and remove it after
the merge:

```
git worktree add .claude/worktrees/feat-x -b feat/x origin/main
git worktree remove .claude/worktrees/feat-x
```

After each merge, update the base clone with one command:

```
./update.sh
```

It refuses if the base clone has local changes or is not on `main`,
fast-forwards it to `origin/main`, lists the commits it brought, re-runs `install.sh` and runs
`guild doctor`. It never edits project configs; through `install.sh` it
re-runs `guild wire-settings`, which only adds what is missing and drops retired ask rules.

`guild doctor` checks, read-only, that every guild hook is wired in
`~/.claude/settings.json` (including `Notification` and `Stop`), that its
`permissions.ask` holds the `party resume` and `raid join` rules (see "Hooks"), that
`~/.claude/GUILD.md` exists and that every project config loads; it exits 1
and names what is missing. It also checks that the guild state commands are in
`permissions.allow` (see "Hooks"); a missing allow rule is a `warn` line and
never changes the exit code. It also warns for a session that leads more than one active party (`session leads 2 active parties: a, b`). It also warns about a project config that still has a `dispatcher` key (ignored, safe to delete). With a global `handoff_margin` (see "Global config") and a recorded compaction it prints `ok      handoff at 76% (compaction 85% − 10%)`, plus a `warn` when that handoff sits less than 5 points above the starting percentage of the latest session (the handoff would fire on a fresh session, so sessions hand off at that start + 5 instead); without a margin it warns when a project's `handoff_threshold` is at or above the last compaction (recorded by the `PreCompact` hook), since that threshold never fires. An invalid `guild.json` fails the check.

`guild doctor --scan-prs` additionally lists the open PRs of every project's
`github.repos` through `gh` and scans title, body, comments and commit
messages with the case-insensitive regex `guild|ask #[0-9]|notice #[0-9]`.
Each match is a `warn` line naming `repo#n` and where it matched
(title/body/comment/commit), never the text. Warnings never change the exit
code; if `gh` fails the scan prints a single `warn` and is skipped. Off by
default so `guild doctor` stays fast and offline.

### Uninstall

```
./uninstall.sh [--purge]
```

Runs `guild unwire-settings` (it removes the hooks and
permission rules from "Hooks" in `~/.claude/settings.json`, keeps every other entry,
copies the previous file to `settings.json.bak` and prints `settings: nothing wired`
when there is nothing to remove) and deletes `~/.local/bin/guild` and
`~/.claude/GUILD.md` when they are symlinks to this clone; any other file there is
left with a `WARN`. The data, config and state directories are kept; `--purge`
deletes them.

It does not edit what it cannot own: remove by hand the line
`@~/.claude/GUILD.md` from `~/.claude/CLAUDE.md` and any `guild hook pre-commit`
line in `~/.config/husky/init.sh` or in a repository's `.git/hooks/pre-commit`.

