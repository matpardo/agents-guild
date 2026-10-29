---
epic: agent-isolation
type: spec
title: OS-level isolation for agent sessions
status: draft
owner: matpardo
created: 2026-10-29
updated: 2026-10-29
---

# Spec: OS-level isolation for agent sessions

## Goal

An agent session cannot change guild state except through the `guild` command, so the rules that keep decisions with the human hold even when an agent tries to bypass them.

## Problem

The hooks read command text, so they are guardrails, not a boundary. An agent running as the same Unix user can write the sqlite database or the project config directly (`python3 -c "import sqlite3..."`), unset or forge `CLAUDE_CODE_SESSION_ID`, or reach git and the CLI through aliases, `eval`, variables and command substitution. Changing the shell does not help: all of these are POSIX or happen outside the shell.

## Scope

- Evaluate the Claude Code Bash sandbox (bubblewrap on Linux): deny writes to the guild data and config dirs from sandboxed commands, run `guild` itself unsandboxed through the excluded-commands setting, and check how strictly that exclusion matches prefixed forms (`env -u ...`, `VAR=x guild ...`).
- One script that tries each known bypass with the sandbox on and off and reports which ones still work.
- Compare with a separate Unix user that owns the database behind a small local service, only if the sandbox leaves a high-severity bypass open.

## Out of scope

- Changing the shell the harness uses.
- Multi-user installs.

## Success criteria

- [ ] With the chosen setup, a direct database write from an agent session fails and every `guild` command an agent may run still works.
- [ ] The README trust model names what the setup closes and what stays open.

## Security and data

Raises the trust boundary from "same Unix user" to "the guild command"; no new data is stored.
