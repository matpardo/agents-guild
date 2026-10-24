---
epic: board-views
type: spec
title: Sidebar and views on the web board
status: active
owner: matpardo
created: 2026-10-23
updated: 2026-10-23
---

# Spec: Sidebar and views on the web board

## Goal

Open the web board and see at a glance where to go: which party works, which is queued, which waits on an ask. Then click in and get the context to decide or review.

## Problem

The board is two long columns of twelve sections, narrowed by party and raid selects. A human scrolls and filters to learn what needs attention, and notices and rarely used sections compete with parties and asks.

## Scope

- A sidebar next to a pane, using the full page width, stacked above the pane on narrow screens.
- Views kept in `location.hash`: needs you (default), one party, one raid, adventurers, ideas, quest board, overview. A view shows only its sections.
- The party and raid selects go away; the sidebar replaces them. The state filter stays.
- The sidebar groups parties by raid, with a solo group for parties outside raids, and shows counts for asks, ready PRs, adventurers, ideas, open quests and new notices.
- The party view shows the whole merge queue of its raids, or its own queue when it has none.
- Party state, ask counts and left work in the sidebar rows (later task).
- Colored resource values (later task).

## Out of scope

- Any change to the CLI or to the board JSON: the web only shows the same model differently.

## Success criteria

- [ ] A human finds the parties that need attention without scrolling.
- [ ] Every view survives a reload and the periodic refresh.
