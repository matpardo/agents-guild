---
epic: realms
type: tasks
title: Realms connect guilds on one network
status: active
updated: 2026-10-24
---

# Tasks: Realms connect guilds on one network

## T01 — Realms epic

**Depends on:** —
**Status:** [x] done

**What:** spec, discovery and tasks for realms; `federation` points at it for the realm.

## T02 — Realm hub

**Depends on:** T01
**Status:** [x] done

**What:** `guild realm init|serve|member`: HTTPS file store with pinned certificate, per-guild tokens, routes and limits.

## T03 — Realm client and status

**Depends on:** T02
**Status:** [ ] pending

**What:** `guild realm join|push|status`: pinned client, counts-only status, local cache, doctor check.

## T04 — Realm panel on the web

**Depends on:** T03
**Status:** [ ] pending

**What:** the board shows the cached realm status and refreshes it through the same command function.

## T05 — Realm file transport

**Depends on:** T03
**Status:** [ ] pending

**What:** `guild realm send|inbox|fetch|drop` in the CLI and the web; agents are denied every realm command but `status`.
