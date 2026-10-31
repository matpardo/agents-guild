# ADR: Core modules do not import command modules

- **Date:** 2026-10-31
- **Status:** accepted

## Context

Command modules under `guild/commands/` are the top layer: they parse arguments and render output. Six core modules (`ask_detail`, `ctx_pressure`, `final_report`, `party_status`, `party_waits`, `realm/snapshot`) imported them to reuse small queries, which inverted the layers and fed import cycles such as the claim, quest and sync loop. It also made every hook run import heavy command modules: the hook path went `hook`, `ctx_pressure`, `party_status`, `next`, `merge_queue`, `raid`, `pr` and `drift` before doing any work on every tool call.

## Decision

Core modules never import `guild.commands`. Only modules under `guild/commands/`, `guild/cli.py` and `guild/webserver.py` may. Logic that both layers need lives in a core module next to its command counterpart: `raid_members`, `notices`, `ideas`, `cards`, `transcripts`, `statusline_state`, `main_status`, `pr_records` and `work_queue`, plus `scoped_queue` in `merge_queue`. Command modules import it from there, with no re-export left behind.

`tests/test_layering.py` fails on any core module importing `guild.commands` and names the offender and the imported module. `tests/test_import_cycles.py` keeps the import graph acyclic.

## Consequences

- Core modules no longer pull command modules in, but the hook still imports ten command modules directly, so hook start time did not change (about 84 ms to import before and after). Faster hooks need `guild/commands/hook.py` itself to import less.
- Command modules shrink to argument handling and rendering; `commands/next.py` keeps only rendering and `run`.
- A new shared query goes into a core module from the start; putting it in a command module and importing it from core fails the suite.
- Callers and tests refer to the core module, so a move touches every call site once.
