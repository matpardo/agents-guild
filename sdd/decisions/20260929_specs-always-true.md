# ADR: Specs are always true

- **Date:** 2026-09-29
- **Status:** accepted

## Context

`sdd/` held draft epics for ideas nobody had started (`skill-integration`, `federation`, and a proposed `install-and-update`). A spec that describes work that does not exist reads like a commitment, drifts from reality without anyone noticing, and `guild` would treat its tasks as real.

## Decision

An epic enters `sdd/` only when its work starts, as `active` with its `tasks.md`, in the PR that starts it. There is no `draft` status; `tests/test_sdd_docs.py` rejects it. Ideas live as GitHub issues until someone takes them.

## Consequences

- Everything in `sdd/` is either in progress or done, so it can be trusted as-is by humans and by `guild next`/`drift`.
- An idea's design discussion happens in its issue, not in a reviewed spec PR; when work starts, the issue text seeds the spec.
- Existing drafts moved to issues #16, #17 and #18.
