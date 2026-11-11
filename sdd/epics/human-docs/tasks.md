---
epic: human-docs
type: tasks
title: Human-friendly docs
status: done
updated: 2026-11-11
---

# Tasks: Human-friendly docs

## T01 — Split README into docs/ verbatim

**Depends on:** —
**Status:** [x] done

**What:** Move the README reference sections into `docs/*.md` without wording changes and fix the pointers to them.

**Acceptance:**
- [x] Every line of the old README is in `README.md` or `docs/`.

## T02 — New README for humans

**Depends on:** T01
**Status:** [x] done

**What:** Rewrite the README with a plain intro, an AI-built and use-at-your-own-risk notice, a lore section, prerequisites and a quickstart.

**Acceptance:**
- [x] A new reader can install and try guild from the README alone.

## T03 — Rewrite the commands reference

**Depends on:** T01
**Status:** [x] done

**What:** Rewrite `docs/commands.md` for readers: grouped by job, one short section per command, design notes moved to decisions, every flag and behavior kept.

**Acceptance:**
- [x] Every command, flag and behavior of the verbatim version is still documented.

## T04 — Rewrite the remaining reference files

**Depends on:** T01
**Status:** [x] done

**What:** Rewrite the other `docs/` files for readers, one file at a time, keeping every key and fact documented.

**Acceptance:**
- [x] Each `docs/` file reads on its own and keeps the facts of the verbatim version.

## T05 — Prepare the repo for public release

**Depends on:** —
**Status:** [x] done

**What:** Name the copyright holder in `LICENSE`, make test fixtures and doc examples domain-neutral, and drop references to private skills from the specs.

**Acceptance:**
- [x] No client-domain wording or private skill names remain in the tree.
