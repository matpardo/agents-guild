---
epic: ideas
type: spec
title: Ideas backlog
status: done
owner: matpardo
created: 2026-10-21
updated: 2026-10-23
---

# Spec: Ideas backlog

## Goal

A place in the CLI and the web board to park loose ideas, so none lives only on a post-it.

## Problem

Ideas arrive while other work is in flight. Today they go on paper or in chat and get lost. Guild has asks and notices, but those are for coordination, not for a personal backlog.

## Scope

- An idea has a title, a description, a creation date and, optionally, a requester (free text), a deadline (`YYYY-MM-DD`) and a registered project.
- Add, edit, delete and list from the CLI and the web, by the human and by sessions.
- The board lists ideas by deadline ascending, no deadline last, and marks the overdue ones.
- Agents delete an idea once they turn it into code, SDD, a card or a quest.
- An idea references the parties and adventurers working on it, and each of them references its ideas, through link entities, from the CLI and the web.
- `README.md` and `GUILD.md` change with the code.

## Out of scope

- Linking ideas to quests or cards automatically.
- Tags, priorities, reminders and notifications.

## Success criteria

- [x] `guild idea add|edit|delete` and `guild ideas [id]` work and survive `guild rebuild`, deletes included.
- [x] The web adds, edits and deletes ideas through the same functions as the CLI.
- [x] Output that leaves the CLI never carries an idea id.

## Security and data

Ideas are local events (visibility `local`). Free text goes through the same email, secret and project-pattern checks as other fields. Web writes need the session token and an allowed origin like every other write.
