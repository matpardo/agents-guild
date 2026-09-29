---
epic: install-and-update
type: spec
title: Versioned install and self-update
status: active
owner: matpardo
created: 2026-09-29
updated: 2026-09-29
---

# Spec: Versioned install and self-update

## Goal

Anyone installs guild with one command and updates it with another, to a released version, without touching their data or config.

## Problem

Today the installed copy is a worktree (`agents-guild-live`) moved by hand after every merge. It works for the person developing guild but not for anyone else, there are no versions to refer to, and nothing tells a user that an update exists. Tools like RTK solve this with tagged releases, an install script and reinstall-to-update.

## Scope

- Tagged releases (`v0.x.y`) with a CHANGELOG.
- `guild version`: installed version and whether a newer release exists.
- An install script that places guild in `~/.local/share/guild/app` pinned to the latest release tag and links `guild` and `GUILD.md`; running it again updates.
- `guild self-update`: move the install to the latest release (or `--to <tag>`); data and config untouched; the database migrates on the next run as it already does.
- The session-start brief mentions a newer release, checked in the background so hooks stay fast.

## Out of scope

- Packaging for pip or other package managers.
- Automatic updates without the user running a command.

## Success criteria

- [ ] A fresh machine goes from nothing to a working `guild` with one command.
- [ ] Updating never changes the database except through its normal migrations, and a failed update leaves the previous version working.

## Security and data

The install and update fetch code from GitHub: pin to tags, verify the fetched tag before switching, and never run code from an unpinned branch. Hooks must never perform network calls in their critical path.
