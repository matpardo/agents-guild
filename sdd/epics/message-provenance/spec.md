---
epic: message-provenance
type: spec
title: Messages show who wrote them and cannot pass as the human
status: draft
owner: matpardo
created: 2026-10-12
updated: 2026-11-11
---

# Spec: Messages show who wrote them and cannot pass as the human

## Goal

An agent can tell what the human said from what another session said, and no text injected by guild can pass as a human order.

## Problem

Notices, asks, answers and handoffs are injected into every session. `notice create` needs no binding and renders as "human" when unbound; any session can run `guild answer`, and the inbox always says "answered by human". Quotes are not escaped, the hook inbox has no end marker, and the raw handoff fallback is unframed. Text such as "dev order" can therefore steer another session.

## Scope

- Secret patterns in `validate_field` (token prefixes, private key headers) next to the email and project patterns.
- Escaped quotes and an end marker in the inbox; the raw handoff fallback and `party resume` framed and stripped.
- Provenance labels: no session means "human", a bound session its party, an unbound session "unbound session", a notice guild creates itself "guild". Applies to the inbox, board and web.
- A PreToolUse hook denies `guild answer` and `guild dismiss` from an agent's tool call. Dev orders count only through an answer given by a human.
- Instruction-like text from non-human sources is shown with a flag, never blocked.

## Out of scope

- Authenticating the web token against local processes: documented as a known limit, since guild is single-user and not a sandbox.
- Labels are not authentication: any process without a Claude session reads as "human" (dev decision 2026-11-11).

## Success criteria

- [ ] A notice from an unbound session never reads "human".
- [ ] An agent's `guild answer` is denied; a human's from a terminal or the web works.
- [ ] A quote inside a notice cannot fake a second item.
- [ ] Text containing a secret pattern is refused at write.

## Security and data

The flag patterns must not match "decisión del dev", the phrase agents are told to use. Flags apply to text from sessions only. Hand-test before T04 whether `!` commands skip PreToolUse and set the session id.

## Decisions

- Agents are denied `guild answer` and `guild dismiss` by a PreToolUse hook, plus provenance labels (decisión del dev, 2026-10-12).
