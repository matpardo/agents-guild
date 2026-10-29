---
epic: agent-isolation
type: tasks
title: OS-level isolation for agent sessions
status: draft
updated: 2026-10-29
---

# Tasks: OS-level isolation for agent sessions

## T01 — Probe the known bypasses under the Bash sandbox

**Depends on:** —
**Status:** [ ] pending

**What:** a script that tries a direct database write, a config write, `env -u CLAUDE_CODE_SESSION_ID guild ...` and a forged session id, with the Claude Code sandbox on and off, and reports which ones still work.

**Acceptance:**
- [ ] The report lists each bypass with its result in both modes.

## T02 — Decide and document the isolation setup

**Depends on:** T01
**Status:** [ ] pending

**What:** pick the sandbox setup (or the separate-user design if the sandbox leaves a high-severity bypass open), record the decision, and update the README trust model and the install docs.

**Acceptance:**
- [ ] A decision record exists and the README trust model matches it.
