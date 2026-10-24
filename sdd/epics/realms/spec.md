---
epic: realms
type: spec
title: Realms connect guilds on one network
status: done
owner: matpardo
created: 2026-10-24
updated: 2026-10-24
---

# Spec: Realms connect guilds on one network

## Goal

The dev sees a summary of every guild of the realm in one place and sends request files from one guild to another without carrying them by hand.

## Problem

Each guild lives on one machine. Requests between teams arrive as md files copied by hand, and the dev has to open each machine to see how its work goes. A realm gives the guilds one channel that shows each guild and carries files, without letting any guild act on another.

## Scope

- A hub that any machine runs with `guild realm serve`, including one that runs a guild. It is a file store with no commands: one status file per guild and one inbox per guild.
- HTTPS with a self-signed certificate pinned by its SHA-256 fingerprint; one token per member guild, stored as a hash on the hub. The sender comes from the token, never from the body.
- Guilds connect only outbound to the hub; the hub never reads or writes a guild database. Nothing remote writes into a guild.
- `guild realm push` sends a status of counts only (per project: parties, open quests, open PRs, ready PRs, open asks, red main). `guild realm status` and the web board show every guild's status.
- `guild realm send|inbox|fetch|drop` carry md files to another guild's inbox. The inbox is for the human: hooks never inject a file into a session.
- Agents may run `guild realm status` only; a PreToolUse hook denies the other realm commands to them.

## Out of scope

- Replicating notices, claims or events between guilds (`federation`).
- Acting on another guild from the realm or from the hub.
- Signing between guilds: the hub is trusted.

## Success criteria

- [x] Two guilds pushed to one hub both show in `guild realm status` and on the web board.
- [x] An md file sent from one guild is fetched byte for byte on the other.
- [x] A client that sees another certificate fingerprint refuses to connect.
- [x] An agent's `guild realm send` is denied.

## Depends on

- `web-board`: the realm panel lives on the board.

## Security and data

The hub is the only process that opens a network port. Tokens and the hub member list live in 0600 files under the guild config dir. The status carries slugs, integers and booleans only, validated by the hub and again by the reader, so no free text crosses in it. Request files are md, UTF-8, at most 256 KB, named by the hub and capped per inbox. A fetched file is written 0600 where the human chooses; it can hold instructions, so the human decides whether an agent ever reads it, as with a file carried by hand today.
