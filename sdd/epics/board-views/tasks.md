---
epic: board-views
type: tasks
title: Sidebar and views on the web board
status: done
updated: 2026-10-26
---

# Tasks: Sidebar and views on the web board

## T01 — Sidebar and views

**Depends on:** —
**Status:** [x] done — #209

**What:** `guild/web/index.html`, `app.js`, `app.css`: a sidebar grouped by raid plus a solo group, and a pane of sections shown per view (`#needs-you`, `#party/<name>`, `#raid/<name>`, `#adventurers`, `#ideas`, `#quests`, `#overview`) kept in the URL hash; the party and raid selects are removed; the party view shows the merge queue of its raids, or its own; full width, stacked under 480px.

## T02 — Party state in the sidebar

**Depends on:** T01
**Status:** [x] done — #210

**What:** `guild/web/app.js`, `app.css`: each sidebar party row shows its state badge, an open-ask count, the work left and `stopped without report`; parties sort by attention inside each group; a raid header shows its worst member state; `.status-queued` gets a blue colour.

## T03 — Colour resource values

**Depends on:** T01
**Status:** [x] done — #211

**What:** `guild/web/app.js`, `app.css`, `index.html`: resource values on the web board are coloured pills (disk percent, RAM available, deltas, `new`, flags, unmeasured states) from named thresholds; the header machine summary is one wrapped line of pills; the sidebar shows a compact disk pill.

## T04 — Live needs-you counts

**Depends on:** T01
**Status:** [x] done

**What:** `guild/web/app.js`, `app.css`: the board refreshes every 10 seconds instead of 15; each sidebar needs-you count above zero (asks, ready, blocked, context high) is a pill coloured by its type, a zero stays muted.

## T05 — Tasks per day

**Depends on:** T01
**Status:** [x] done

**What:** `guild/commands/board.py`, `guild/web/app.js`, `app.css`, `index.html`: each party model carries `daily_tasks`, the tasks created and done per local day over the last 15 days; the party and raid views show them as a table under the merge queue (a raid sums its members), and `guild board --party|--raid` prints the same rows.

## T06 — Rest days in tasks per day

**Depends on:** T05
**Status:** [x] done

**What:** `guild/commands/board.py`, `guild/web/app.js`: each `daily_tasks` day carries `active`, true when a session of the party recorded an event that day; the CLI rows and the web table show `-` for an inactive day with no task created or done, so a day the party was off reads apart from a day a session produced nothing.
