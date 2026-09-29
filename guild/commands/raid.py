from guild import config, db, events, identity, names, timeutil
from guild.errors import GuildError


def join(ctx, name, ttl):
    names.validate_name(name, "raid name")
    binding = identity.require_binding(ctx.conn, ctx.session_id)
    project = config.resolve_project(ctx.cwd, config.load_all_projects(ctx.projects_dir))
    expires_at = timeutil.expires_at_iso(ctx.now, ttl)
    with db.writing(ctx.conn):
        events.record(
            ctx.conn,
            ctx.now,
            ctx.origin,
            binding["party"],
            ctx.session_id,
            project,
            "raid.joined",
            "local",
            {"raid": name, "party": binding["party"], "expires_at": expires_at},
        )
    return "party '{}' joined raid '{}' until {}".format(binding["party"], name, expires_at)


def leave(ctx, name):
    names.validate_name(name, "raid name")
    binding = identity.require_binding(ctx.conn, ctx.session_id)
    row = ctx.conn.execute(
        "SELECT expires_at FROM raid_members WHERE raid = ? AND party = ?",
        (name, binding["party"]),
    ).fetchone()
    if row is None or timeutil.is_expired(ctx.now, row["expires_at"]):
        raise GuildError(
            "party '{}' is not a member of raid '{}'".format(binding["party"], name), 1
        )
    project = config.resolve_project(ctx.cwd, config.load_all_projects(ctx.projects_dir))
    with db.writing(ctx.conn):
        events.record(
            ctx.conn,
            ctx.now,
            ctx.origin,
            binding["party"],
            ctx.session_id,
            project,
            "raid.left",
            "local",
            {"raid": name, "party": binding["party"]},
        )
    return "party '{}' left raid '{}'".format(binding["party"], name)


def active_members(conn, now, raid_name):
    rows = conn.execute("SELECT * FROM raid_members WHERE raid = ?", (raid_name,)).fetchall()
    return [row for row in rows if not timeutil.is_expired(now, row["expires_at"])]


def member_raids(conn, now, party):
    rows = conn.execute("SELECT * FROM raid_members WHERE party = ?", (party,)).fetchall()
    return [row for row in rows if not timeutil.is_expired(now, row["expires_at"])]


def member_raid_names(conn, now, party):
    if party is None:
        return set()
    return {row["raid"] for row in member_raids(conn, now, party)}


def list_raids(ctx):
    rows = ctx.conn.execute("SELECT * FROM raid_members ORDER BY raid ASC, party ASC").fetchall()
    by_raid = {}
    for row in rows:
        if timeutil.is_expired(ctx.now, row["expires_at"]):
            continue
        by_raid.setdefault(row["raid"], []).append(row)
    lines = []
    for raid_name in sorted(by_raid):
        lines.append("{}:".format(raid_name))
        for row in by_raid[raid_name]:
            lines.append(
                "  {} ({})".format(row["party"], timeutil.time_left_label(ctx.now, row["expires_at"]))
            )
    return lines
