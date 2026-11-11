---
epic: install-and-update
type: spec
title: Versioned install and self-update
status: active
owner: matpardo
created: 2026-09-29
updated: 2026-11-11
---

# Spec: Versioned install and self-update

## Goal

Anyone installs guild with one command and updates it with another, to a released version, without touching their data or config.

## Problem

Today the installed copy is a worktree (`agents-guild-live`) moved by hand after every merge. It works for the person developing guild but not for anyone else, there are no versions to refer to, and nothing tells a user that an update exists. Tools like RTK solve this with tagged releases, an install script and reinstall-to-update.

## Scope

- Semver release tags (`v0.x.y`) with a GitHub Release whose notes come from PR titles.
- `guild --version`: the installed version, from `git describe` of the clone.
- Install from a base clone kept on `main` (`./install.sh`); update with `./update.sh` (ADR `20261021_worktrees-inside-base-clone.md`).

## Out of scope

- Packaging for pip or other package managers.
- A managed install directory pinned to a release, `guild self-update` and a newer-release hint: superseded by the base-clone install (ADR `20261008_base-clone-install.md`).
- Automatic updates without the user running a command.

## Success criteria

- [ ] A fresh machine goes from nothing to a working `guild` with one command.
- [ ] Updating never changes the database except through its normal migrations, and a failed update leaves the previous version working.

## Security and data

The install and update fetch code from GitHub: pin to tags, verify the fetched tag before switching, and never run code from an unpinned branch. Hooks must never perform network calls in their critical path.
