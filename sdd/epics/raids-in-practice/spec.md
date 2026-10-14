---
epic: raids-in-practice
type: spec
title: Raids that protect parallel work on one epic
status: active
owner: matpardo
created: 2026-09-29
updated: 2026-10-14
---

# Spec: Raids that protect parallel work on one epic

## Goal

Several parties develop one epic in parallel without colliding: shared files are guarded for every editor, merges announce themselves, raid membership does not vanish silently and task lists cannot overlap.

## Problem

Preparing the first real raid (three parties running `/epic-auto-full` under `/goal`, one leading) showed that the rules lived in prose: the claim instruction never reaches the `coder` subagents that actually edit, merges must be announced by hand, membership expires by TTL without warning, and nothing stops two parties from taking the same task.

## Scope

- A `PreToolUse` guard on file edits that claims shared areas for the editing party and denies edits to areas another party holds. Verified: hooks fire on subagent tool calls with the parent `session_id` and `agent_id`/`agent_type`, and a deny reason reaches the subagent verbatim.
- Automatic raid notices when a tracked PR is merged, listing shared areas it touched.
- Raid membership that lasts until leave, or an explicit TTL, with a warning before expiry.
- No overlapping task lists: `quest add` rejects taken tasks; `claim check` for orchestrators.
- A raid lead, visible everywhere, who also receives members' asks. Retired on 2026-10-14 (`sdd/decisions/20261014_board-shows-waits-no-dispatcher.md`): members' asks go to the human, and pins and pause belong to every active member.
- Terminal and web board filtered by raid; better unknown-project errors.

## Out of scope

- Changing `/epic-auto-full` itself; it can call `guild claim check`.

## Success criteria

- [ ] An edit by a subagent to a shared file held by another party is denied with the holder named.
- [ ] A merge of a tracked PR reaches every other party of the raid without anyone posting it.

## Security and data

The edit guard only reads the file path and the local database; it never blocks when guild cannot resolve a party or project. Notices carry PR numbers, tasks and file paths only.
