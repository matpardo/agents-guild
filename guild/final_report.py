from guild.commands import idea as idea_commands

_CLOSED_LIFECYCLES = ("merged", "closed")


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
        "quest {}: {}/{} tasks done ({})".format(row["slug"], row["done"], row["total"], row["state"])
        for row in quests
    )
    lines.extend("idea #{}: {}".format(row["id"], row["title"]) for row in idea_commands.linked_ideas(ctx, party))
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
    lines.append("pending: {}".format(pending))
    return "\n".join(lines)
