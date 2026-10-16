---
epic: derived-state
type: tasks
title: Flags that follow the events that resolve them
status: done
updated: 2026-10-11
---

# Tasks: Flags that follow the events that resolve them

## T01 — Derived needs-ask-answer

**Depends on:** —
**Status:** [x] done — #124

**What:** a PR counts as `needs-ask-answer` while the manual flag is set or an open ask refs it (`pr:<owner/repo>#<n>`), computed at read time through one shared SQL fragment (`guild/pr_asks.py`) so nothing is stored and nothing goes stale. The merge queue, `ready-check`, the board, the web PR pill and the dispatcher promote and cap checks all read it, and name the ask: `needs ask answer (ask #N)`. `pr set --no-needs-ask-answer` clears only the manual flag; an open ask keeps blocking until it is answered or dismissed.

**Acceptance:**
- [x] An open ask on the PR blocks it in the merge queue with `(ask #N)`; answering or dismissing it unblocks the PR with no `pr set`.
- [x] The manual flag still blocks without an ask, and `--no-needs-ask-answer` does not hide an open ask.
- [x] The text board and the web board model carry the ask id; the web pill names it.
- [x] The dispatcher does not promote a PR with an open ask.

## T02 — Red-main pre-push guard

**Depends on:** —
**Status:** [x] done — #124

**What:** `guild hook pre-push` refuses a push while the repo's main is red, naming the checks and since when, and the way out: fix main first, or flag the PR with `guild pr set <ref> --fixes-main`. A push from the branch of an open tracked PR flagged `fixes_main` passes; with no main status the hook stays silent. The merge queue already puts `fixes_main` PRs first and shows `MAIN RED`, and the web board already shows the main-red row; only flags backed by an event (`needs-ask-answer`) expire, no expiry is built for the other flags.

**Acceptance:**
- [x] A push is refused while main is red, with reason and the way out.
- [x] A push from a `fixes_main` PR branch is allowed; so is any push when main is green or unknown.

## T03 — Coherence pass over the readme and agent rules

**Depends on:** T01
**Status:** [x] done — #125

**What:** the README lists every dispatcher rule, project config key, CLI command and web page or write route that the code registers, with no stale statement left by earlier PRs; `GUILD.md` matches the current CLI (external block, derived `needs-ask-answer`, finding record, ready-check, caps, red-main push); a root `CLAUDE.md` holds the rules for developing guild itself.

**Acceptance:**
- [x] The dispatcher table, the project config list and the command list match `guild/dispatch_rules.py`, `guild/config.py` and `guild/cli.py`.
- [x] `GUILD.md` names each agent-visible behavior added since it was last revised.
- [x] `CLAUDE.md` exists and every claim in it is checked against the repo.

## T04 — Red main gates Ready instead of every push

**Depends on:** T02
**Status:** [x] done — #166

**What:** with main red (not blocked by billing) a push from a branch with no PR or a draft PR passes with a warning to keep iterating in draft; a push to a Ready PR, `gh pr ready` without `--undo` and `gh pr create` without `--draft` are refused, since they would fire CI on red main. Only a PR flagged `fixes_main` is exempt; `fixes_flaky` is not. The checks live in `guild hook pre-push` and accept `gh -R <repo> pr ...` forms (decisión del dev, 2026-10-15).

**Acceptance:**
- [x] A push from a draft PR or a branch without PR passes with a warning; a push to a Ready PR is refused with the way out.
- [x] `gh pr ready` and a non-draft `gh pr create` are refused while main is red; `gh pr ready --undo` and `gh pr create --draft` pass.
- [x] A `fixes_main` PR passes every check; billing only warns.

## T05 — Push and PR hooks follow cd and flag=value forms

**Depends on:** T04
**Status:** [x] done — #167

**What:** `guild hook pre-push` and `pre-pr-owner` follow `cd <dir>` segments of a chained command, so `cd <worktree> && git push` resolves the branch of that worktree; a `cd` that cannot be resolved makes a later push or `gh pr ready|create` warn as unresolved. `--repo=<r>` and `--head=<b>` are parsed, and `gh pr create -fd` counts as draft.

**Acceptance:**
- [x] A push to a Ready PR after `cd <worktree>` is refused while main is red; a draft PR only warns.
- [x] An unresolvable `cd` before a push gives the unresolved warning.
- [x] `--repo=` and `--head=` forms and bundled `-fd` are recognized.
