---
epic: human-docs
type: tasks
title: Human-friendly docs
status: active
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
**Status:** [ ] pending

**What:** Rewrite the README with a plain intro, an AI-built and use-at-your-own-risk notice, a lore section, prerequisites and a quickstart.

**Acceptance:**
- [ ] A new reader can install and try guild from the README alone.

## T03 — Rewrite reference per docs file

**Depends on:** T01
**Status:** [ ] pending

**What:** Rewrite each `docs/` file for readers, one file at a time, keeping every command and key documented.

**Acceptance:**
- [ ] Each `docs/` file reads on its own and keeps the facts of the verbatim version.
