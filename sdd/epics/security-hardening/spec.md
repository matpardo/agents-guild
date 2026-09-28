---
epic: security-hardening
type: spec
title: Security hardening from the internal audit
status: done
owner: matpardo
created: 2026-09-28
updated: 2026-09-28
---

# Spec: Security hardening from the internal audit

## Goal

Close the eight findings of the internal security audit without changing how guild is used.

## Problem

The pre-push guard failed open on common command shapes; names could escape their directories; free text from other sessions, SDD and `gh` reached agents and terminals unlabeled and unsanitized; nothing stopped personal data; files were world-readable.

## Scope

- Pre-push detection for wrapped, nested and chained commands; unresolved branch warns instead of allowing silently.
- Name validation and path containment.
- Control-sequence stripping at ingestion and render; one-line framing for injected messages.
- Length caps, email rejection, per-project `pii_patterns`, broadcast reminder.
- Private file modes; install that never clobbers foreign files; documented trust model.

## Out of scope

- Authenticating hook stdin: guild is single-user by design.

## Success criteria

- [x] Every audit finding has a regression test.
- [x] Blocked on a real merged branch in every command shape.

## Security and data

This epic is the security baseline; new free-text fields must go through the same caps and screening.
