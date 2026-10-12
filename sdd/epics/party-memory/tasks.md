---
epic: party-memory
type: tasks
title: What a party learns survives across generations
status: draft
updated: 2026-10-12
---
# Tasks: What a party learns survives across generations

## T01 — Store, CLI and web

**Depends on:** —
**Status:** [ ] pending

**What:** memory items per party with `guild memory add|list|rm` and a web view with delete through `sendPost`. Storage is one markdown file per item under `data_dir/memory/<party>/`; guild owns writes and the directory is not rebuilt from events.

## T02 — Handoff appends what it learned

**Depends on:** T01
**Status:** [ ] pending

**What:** `guild handoff` adds `--learned` to the party memory, skipping identical text.

## T03 — Injection and brief fix

**Depends on:** T01
**Status:** [ ] pending

**What:** SessionStart injects the memory framed with an end marker and a cap; the brief's handoff section keeps In flight and Learned and wraps long lines instead of cutting at 300.
