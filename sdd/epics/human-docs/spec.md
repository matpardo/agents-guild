---
epic: human-docs
type: spec
title: Human-friendly docs
status: done
owner: matpardo
created: 2026-11-11
updated: 2026-11-11
---

# Spec: Human-friendly docs

## Goal

Make guild's docs readable by a person who has never seen the tool: a short README to get started and a reference split by topic.

## Problem

The README grew to more than 3,000 lines. A new reader meets the full reference before knowing what guild is, what it needs or how to try it.

## Scope

- A short README: a plain intro, a notice that the tool is built with AI and used at your own risk, a lore section, prerequisites, a quickstart and links to the reference.
- The reference split by topic under `docs/` (concepts, commands, configuration, hooks, data, realms, development), first moved verbatim.
- Each reference file rewritten for readers, one file at a time.

## Out of scope

- Behavior changes: the commands, flags and config keys stay as they are.
- `GUILD.md` rules, except pointers to moved sections.

## Success criteria

- [ ] The README fits one screen of install and quickstart steps and links every file under `docs/`.
- [ ] No text of the old README is lost in the split.
- [ ] Each `docs/` file reads from top to bottom without the others.

## Security and data

N/A: documentation only.
