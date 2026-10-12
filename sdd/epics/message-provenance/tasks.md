---
epic: message-provenance
type: tasks
title: Messages show who wrote them and cannot pass as the human
status: draft
updated: 2026-10-12
---
# Tasks: Messages show who wrote them and cannot pass as the human

## T01 — Secret patterns

**Depends on:** —
**Status:** [x] done — #136

**What:** `validate_field` refuses common token prefixes and private key headers.

## T02 — Framing

**Depends on:** —
**Status:** [ ] pending

**What:** escape quotes and add an end marker in the inbox; frame and strip the raw handoff in `hook._resume_lines` and `party resume`.

## T03 — Provenance labels

**Depends on:** —
**Status:** [ ] pending

**What:** record whether the author was unbound; label human, party or unbound session in inbox, board and web. Old events read as human.

## T04 — Agents cannot answer

**Depends on:** T03
**Status:** [ ] pending

**What:** PreToolUse hook on Bash, built like `pre-pr-owner`, denies `guild answer` and `guild dismiss`.

## T05 — Flag instruction-like text

**Depends on:** T02
**Status:** [ ] pending

**What:** flag patterns in non-human text, shown never blocked; test that "decisión del dev" is not flagged.
