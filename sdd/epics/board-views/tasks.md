---
epic: board-views
type: tasks
title: Sidebar and views on the web board
status: done
updated: 2026-10-23
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
