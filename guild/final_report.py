from guild import identity, timeutil
from guild.commands import idea as idea_commands

_CLOSED_LIFECYCLES = ("merged", "closed")

STALE_PR_NOTE = "(PR state as of last sync)"


def _pr_lines(rows):
    lines = []
    for row in rows:
        state = row["lifecycle"] if row["lifecycle"] in _CLOSED_LIFECYCLES else "open"
        lines.append("  {}#{} | {} | {}".format(row["repo"], row["number"], row["what"], state))
    return lines


def _pr_section(rows):
    if not rows:
        return ["PRs: none"]
    return ["PRs (ref | what | state):"] + _pr_lines(rows)


def _ask_lines(ctx, label):
    rows = ctx.conn.execute("SELECT id, state, question FROM asks WHERE party = ? ORDER BY id", (label,)).fetchall()
    return ["ask #{} ({}): {}".format(row["id"], row["state"], row["question"]) for row in rows]


def _created_idea_lines(ctx, label, linked_ids):
    rows = ctx.conn.execute(
        "SELECT ideas.id AS id, ideas.title AS title FROM events"
        " JOIN ideas ON ideas.id = json_extract(events.payload, '$.id')"
        " WHERE events.kind = 'idea.created' AND events.party = ? ORDER BY ideas.id",
        (label,),
    ).fetchall()
    return ["idea #{} created: {}".format(row["id"], row["title"]) for row in rows if row["id"] not in linked_ids]


def _open_quest_lines(ctx, session_ids):
    placeholders = ", ".join("?" for _ in session_ids)
    rows = ctx.conn.execute(
        "SELECT quests.slug AS slug, quests.party AS party FROM events"
        " JOIN quests ON quests.slug = json_extract(events.payload, '$.slug')"
        " WHERE events.kind = 'quest.added' AND json_extract(events.payload, '$.party') IS NULL"
        " AND events.session_id IN ({}) ORDER BY quests.slug".format(placeholders),
        tuple(session_ids),
    ).fetchall()
    return [
        "open quest {}: {}".format(row["slug"], "no party yet" if row["party"] is None else "taken by " + row["party"])
        for row in rows
    ]


def _notice_lines(ctx, label):
    rows = ctx.conn.execute(
        "SELECT id, text, expires_at FROM notices WHERE party = ? AND state = 'active' ORDER BY id", (label,)
    ).fetchall()
    return [
        "notice #{} (until {}): {}".format(row["id"], timeutil.issued_label(row["expires_at"]), row["text"])
        for row in rows
        if not timeutil.is_expired(ctx.now, row["expires_at"])
    ]


def _generated_lines(ctx, label, session_ids, linked_ids):
    return (
        _ask_lines(ctx, label)
        + _created_idea_lines(ctx, label, linked_ids)
        + _open_quest_lines(ctx, session_ids)
        + _notice_lines(ctx, label)
    )


def _plural(count, word):
    return "{} {}{}".format(count, word, "" if count == 1 else "s")


def _open_work_warning(ctx, label, prs):
    open_asks = ctx.conn.execute(
        "SELECT COUNT(*) AS n FROM asks WHERE party = ? AND state = 'open'", (label,)
    ).fetchone()["n"]
    open_prs = len([row for row in prs if row["lifecycle"] not in _CLOSED_LIFECYCLES])
    parts = []
    if open_asks:
        parts.append(_plural(open_asks, "ask"))
    if open_prs:
        parts.append(_plural(open_prs, "PR"))
    if not parts:
        return []
    return ["warning: left open: {}".format(", ".join(parts))]


def party_report(ctx, party, pending):
    prs = ctx.conn.execute(
        "SELECT repo, number, what, lifecycle FROM prs WHERE party = ? ORDER BY repo ASC, number ASC", (party,)
    ).fetchall()
    quests = ctx.conn.execute(
        "SELECT quests.slug AS slug, quests.state AS state,"
        " (SELECT COUNT(*) FROM quest_tasks WHERE quest_tasks.quest = quests.slug) AS total,"
        " (SELECT COUNT(*) FROM quest_tasks WHERE quest_tasks.quest = quests.slug AND quest_tasks.state = 'done')"
        " AS done FROM quests WHERE quests.party = ? ORDER BY quests.slug ASC",
        (party,),
    ).fetchall()
    lines = ["final report for party '{}':".format(party)]
    lines.extend(_pr_section(prs))
    lines.extend(
        "quest {}: {}/{} tasks done ({})".format(row["slug"], row["done"], row["total"], row["state"]) for row in quests
    )
    linked = idea_commands.linked_ideas(ctx, party)
    lines.extend("idea #{}: {}".format(row["id"], row["title"]) for row in linked)
    session_ids = [
        row["session_id"]
        for row in ctx.conn.execute(
            "SELECT session_id FROM leaders WHERE party = ? AND session_id IS NOT NULL", (party,)
        )
    ]
    lines.extend(_generated_lines(ctx, party, session_ids, {row["id"] for row in linked}))
    lines.append("pending: {}".format(pending))
    return "\n".join(lines)


def adventurer_report(ctx, adventurer, pending):
    prs = ctx.conn.execute(
        "SELECT repo, number, what, lifecycle FROM prs WHERE adventurer = ? ORDER BY repo ASC, number ASC",
        (adventurer["id"],),
    ).fetchall()
    lines = ["final report for adventurer {}:".format(adventurer["id"]), "job: {}".format(adventurer["job"])]
    if adventurer["task"] is not None:
        lines.append("task: {}".format(adventurer["task"]))
    lines.extend(_pr_section(prs))
    label = identity.adventurer_label(adventurer["id"])
    lines.extend(_generated_lines(ctx, label, [ctx.session_id], set()))
    lines.extend(_open_work_warning(ctx, label, prs))
    lines.append("pending: {}".format(pending))
    return "\n".join(lines)
