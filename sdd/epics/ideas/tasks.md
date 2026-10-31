---
epic: ideas
type: tasks
title: Ideas backlog
status: done
updated: 2026-10-31
---

# Tasks: Ideas backlog

## T01 — Ideas data, commands and CLI

**Depends on:** —
**Status:** [x] done — #189

**What:** `ideas` table, `idea.created`, `idea.edited` and `idea.deleted` events, `guild idea add|edit|delete` and `guild ideas [id]`.

**Acceptance:**
- [x] Ideas sort by deadline, no deadline last, overdue marked, and survive `guild rebuild`.

## T02 — Ideas on the web board

**Depends on:** T01
**Status:** [x] done — #189

**What:** `ideas` in the board model, the `POST /api/ideas/*` routes and an ideas section with form, inline edit and delete.

**Acceptance:**
- [x] The web creates, edits and deletes ideas and shows the overdue ones.

## T03 — Ideas docs and agent rule

**Depends on:** T01
**Status:** [x] done — #189

**What:** `README.md` command reference and Ideas section, one `GUILD.md` rule, and the trace guard covering idea ids.

**Acceptance:**
- [x] `GUILD.md` tells agents to delete an idea once it is turned into work.

## T04 — Idea form inputs

**Depends on:** T02
**Status:** [x] done — #190

**What:** The web deadline is typed as `YYYY-MM-DD` and the project select lists every registered project.

**Acceptance:**
- [x] The deadline input is a text field asking for `YYYY-MM-DD`, and the select lists all registered projects with a `no project` choice.

## T05 — Link ideas to parties

**Depends on:** T01
**Status:** [x] done — #203

**What:** `guild idea link|unlink` and `POST /api/ideas/<id>/link|unlink` tie an idea to the parties working on it; `guild ideas`, `guild board` and the web show both sides, and `GUILD.md` tells a party to link the idea it starts from.

**Acceptance:**
- [x] A session links and unlinks its own party; the human terminal passes `--party`; unknown or closed parties, unknown ideas and double links are refused.
- [x] `guild ideas` shows `worked by:` and the party block in `guild board` lists its ideas, and the links survive `guild rebuild` and vanish with the idea.
- [x] The web links and unlinks through the same functions as the CLI.

## T06 — Idea description box, dates and link status

**Depends on:** T05
**Status:** [x] done

**What:** The web description is a multi-line text box whose line breaks are kept on view; each idea shows its created date and, after an edit, its updated date; an idea with no linked party says `not linked yet` in the CLI and the web.

**Acceptance:**
- [x] The web description field is a textarea and the view keeps its line breaks.
- [x] `guild ideas <id>` and the web show `created` and, after an edit, `updated` in local time.
- [x] An unlinked idea shows `not linked yet` in `guild ideas`, `guild ideas <id>` and the web.

## T07 — Keep an idea linked once its party tracks a PR

**Depends on:** T05
**Status:** [x] done

**What:** `guild idea unlink` and the web `Unlink` are refused once the party tracks a PR (any lifecycle); untracking the PRs releases the lock. Linking and `guild idea delete` stay allowed.

**Acceptance:**
- [x] `guild idea unlink` fails with a message naming the idea and the party while the party tracks a PR, for a session and for the human `--party` path; the link survives.
- [x] After `guild pr untrack` the unlink works.
- [x] The board model carries `has_prs` per linked party and the web shows no `Unlink` for it.

## T08 — Let adventurers link the ideas they work on

**Depends on:** T07
**Status:** [x] done

**What:** An adventurer session runs `guild idea link <id>` and `unlink` for itself, the human passes `--adventurer <id>`, and the web links and unlinks adventurers through the same functions. The link shows in `guild ideas`, the board (CLI and web) and the `adventurer done` final report; promoting an adventurer moves its links to the party.

**Acceptance:**
- [x] `guild idea link|unlink` from an adventurer session acts for its own adventurer; a session cannot act for another party or adventurer.
- [x] The adventurer must be active to be linked; unlink is refused once the adventurer tracks a PR.
- [x] `guild ideas`, the board and the web show the adventurer next to the parties; the final report lists the idea.
- [x] `guild adventurer promote` moves the links to the new party.
