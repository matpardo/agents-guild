from guild import render
from guild.commands import claim as claim_commands
from guild.commands import notice as notice_commands


def _party_section(ctx, party_row):
    lines = ["party: {} ({})".format(party_row["name"], party_row["state"])]
    quests = ctx.conn.execute(
        "SELECT slug, title FROM quests WHERE party = ? AND state = 'active'", (party_row["name"],)
    ).fetchall()
    for quest in quests:
        lines.append("  quest: {} — {}".format(quest["slug"], quest["title"]))
        lanes = render.quest_lanes(ctx.conn, quest["slug"])
        for lane_name in ("active", "queued", "blocked"):
            if lanes[lane_name]:
                lines.append("    {}: {}".format(lane_name, ", ".join(lanes[lane_name])))
    prs = ctx.conn.execute("SELECT * FROM prs WHERE party = ?", (party_row["name"],)).fetchall()
    for pr_row in prs:
        lines.append("  " + render.pr_line(pr_row))
    open_asks = ctx.conn.execute(
        "SELECT COUNT(*) AS n FROM asks WHERE party = ? AND state = 'open'", (party_row["name"],)
    ).fetchone()["n"]
    active_notices = len(
        [row for row in notice_commands.active_notices(ctx.conn, ctx.now) if row["party"] == party_row["name"]]
    )
    active_claims = len(
        [row for row in claim_commands.list_claims(ctx.conn, ctx.now) if row["party"] == party_row["name"]]
    )
    lines.append(
        "  open asks: {}  notices: {}  claims: {}".format(open_asks, active_notices, active_claims)
    )
    return lines


def render_board(ctx, party_filter):
    if party_filter is not None:
        rows = ctx.conn.execute("SELECT * FROM parties WHERE name = ?", (party_filter,)).fetchall()
    else:
        rows = ctx.conn.execute("SELECT * FROM parties ORDER BY name ASC").fetchall()
    lines = []
    for row in rows:
        lines.extend(_party_section(ctx, row))
    return lines
