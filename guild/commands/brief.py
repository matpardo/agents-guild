from guild import config, identity, localbase, pii, render
from guild.commands import claim as claim_commands
from guild.commands import inbox as inbox_commands
from guild.commands import notice as notice_commands
from guild.commands import raid as raid_commands
from guild.identity import UNBOUND_HINT


def _resolve_project(ctx):
    projects = config.load_all_projects(ctx.projects_dir)
    return config.resolve_project(ctx.cwd, projects)


def _base_warning_lines(ctx, project_name):
    lines = []
    for project in config.load_all_projects(ctx.projects_dir):
        if project["name"] == project_name:
            lines.extend(localbase.behind_warning_lines(project))
    return lines


def _targeting_lines(rows, project, raid_member_of):
    matched = notice_commands.targeting(rows, project, True, raid_member_of)
    lines = [notice_commands.format_notice_line(row["id"], row["party"], row["text"]) for row in matched]
    return inbox_commands.framed(lines)


def render_brief(ctx):
    if ctx.session_id is None:
        return ["brief is the per-session view for agents; from a terminal use `guild board` and `guild asks`"]
    binding = identity.resolve_binding(ctx.conn, ctx.session_id)
    active = notice_commands.active_notices(ctx.conn, ctx.now)
    if binding is None:
        project = _resolve_project(ctx)
        lines = [UNBOUND_HINT]
        lines.extend(_targeting_lines(active, project, set()))
        lines.extend(_base_warning_lines(ctx, project))
        lines.append(pii.LOCAL_ONLY_REMINDER)
        return lines

    lines = ["party: {} (generation {})".format(binding["party"], binding["generation"])]
    quests = ctx.conn.execute(
        "SELECT slug, title FROM quests WHERE party = ? AND state = 'active'", (binding["party"],)
    ).fetchall()
    for quest in quests:
        lines.append("quest: {} — {}".format(quest["slug"], quest["title"]))
        lanes = render.quest_lanes(ctx.conn, quest["slug"])
        for lane_name in ("active", "queued", "blocked"):
            if lanes[lane_name]:
                lines.append("  {}: {}".format(lane_name, ", ".join(lanes[lane_name])))

    prs = ctx.conn.execute("SELECT * FROM prs WHERE party = ?", (binding["party"],)).fetchall()
    for pr_row in prs:
        lines.append(render.pr_line(pr_row))

    my_open_asks = ctx.conn.execute(
        "SELECT COUNT(*) AS n FROM asks WHERE party = ? AND state = 'open'", (binding["party"],)
    ).fetchone()["n"]
    total_open_asks = ctx.conn.execute(
        "SELECT COUNT(*) AS n FROM asks WHERE state = 'open'"
    ).fetchone()["n"]
    lines.append("open asks: {} mine, {} total".format(my_open_asks, total_open_asks))

    raids = raid_commands.member_raids(ctx.conn, ctx.now, binding["party"])
    raid_member_of = {row["raid"] for row in raids}
    lines.extend(_targeting_lines(active, binding["project"], raid_member_of))
    for raid_row in raids:
        lead_row = raid_commands.active_lead(ctx.conn, ctx.now, raid_row["raid"])
        if lead_row is not None:
            lines.append("raid {} — lead: {}".format(raid_row["raid"], lead_row["party"]))

    lines.extend(_base_warning_lines(ctx, binding["project"]))

    claims = [row for row in claim_commands.list_claims(ctx.conn, ctx.now) if row["party"] == binding["party"]]
    for claim_row in claims:
        lines.append("claim: {} until {}".format(claim_row["area"], claim_row["expires_at"]))

    lines.append(pii.LOCAL_ONLY_REMINDER)
    return lines
