---
epic: party-memory
type: spec
title: What a party learns survives across generations
status: draft
owner: matpardo
created: 2026-10-12
updated: 2026-10-12
---

# Spec: What a party learns survives across generations

## Goal

Each party keeps a small memory that every later generation receives, for any model, written only on purpose by the agent.

## Problem

`--learned` reaches generation N+1 only, and the brief cuts handoff lines to 300 characters behind sections it already shows, so "Learned" is the first thing lost. Claude Code's auto-memory is shared by all parties and works only for Claude.

## Scope

- Per-party memory as a markdown directory `data_dir/memory/<party>/` (decision del dev, 2026-10-12), contained with `names.ensure_within`, managed by guild: `guild memory add|list|rm` and a web view with delete.
- `handoff --learned` appends to the memory, skipping identical text.
- SessionStart injects it framed as local data, newest first, capped at about 1500 characters, with an end marker.
- The brief's handoff section keeps only "In flight" and "Learned", wrapped instead of cut.

## Out of scope

- Search tooling: Basic Memory over the same directory is a later step if search is needed.
- Memory shared across parties or projects.
- Any automatic capture of tool output or transcripts.

## Success criteria

- [ ] A learning written in generation 1 reaches generation 3 without being copied by hand.
- [ ] A human can list and remove any item from the CLI and the web.
- [ ] Memory never exceeds its cap in the injected text.

## Security and data

Only text the agent writes is stored, checked by `validate_field` and the secret patterns of `message-provenance`; 500 characters per item. Memory is local, never exported, and injected as data, not instructions. A poisoned item stays inside one party.
