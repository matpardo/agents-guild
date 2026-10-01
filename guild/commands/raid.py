from guild import config, db, events, identity, names, timeutil
from guild.errors import GuildError


def _join_label(expires_at):
    if expires_at is None:
        return "until leave"
    return "until {}".format(expires_at)


def _resolve_lead_flag(conn, now, raid_name, party, lead_requested):
    current_lead = active_lead(conn, now, raid_name)
    if lead_requested:
        if current_lead is not None and current_lead["party"] != party:
            raise GuildError(
                "raid '{}' already has a lead: party '{}'".format(raid_name, current_lead["party"]), 1
            )
        return True
    return current_lead is not None and current_lead["party"] == party


def join(ctx, name, ttl, until_leave, lead):
    names.validate_name(name, "raid name")
    binding = identity.require_binding(ctx.conn, ctx.session_id)
    project = config.resolve_project(ctx.cwd, config.load_all_projects(ctx.projects_dir))
    expires_at = None if until_leave else timeutil.expires_at_iso(ctx.now, ttl)
    is_lead = _resolve_lead_flag(ctx.conn, ctx.now, name, binding["party"], lead)
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
            {"raid": name, "party": binding["party"], "expires_at": expires_at, "lead": is_lead},
        )
    return "party '{}' joined raid '{}' {}".format(binding["party"], name, _join_label(expires_at))


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


def active_lead(conn, now, raid_name):
    for row in active_members(conn, now, raid_name):
        if row["lead"]:
            return row
    return None


def led_raid_names(conn, now, party):
    rows = conn.execute("SELECT DISTINCT raid FROM raid_members WHERE lead = 1 AND party = ?", (party,)).fetchall()
    led = []
    for row in rows:
        lead_row = active_lead(conn, now, row["raid"])
        if lead_row is not None and lead_row["party"] == party:
            led.append(row["raid"])
    return sorted(led)


def require_active_raid(conn, now, raid_name):
    members = active_members(conn, now, raid_name)
    if not members:
        raise GuildError("raid '{}' has no active members".format(raid_name), 1)
    return members


def member_raids(conn, now, party):
    rows = conn.execute("SELECT * FROM raid_members WHERE party = ?", (party,)).fetchall()
    return [row for row in rows if not timeutil.is_expired(now, row["expires_at"])]


def member_raid_names(conn, now, party):
    if party is None:
        return set()
    return {row["raid"] for row in member_raids(conn, now, party)}


def raid_names_led_by_for_member(conn, now, lead_party, member_party):
    result = []
    for row in member_raids(conn, now, member_party):
        lead_row = active_lead(conn, now, row["raid"])
        if lead_row is not None and lead_row["party"] == lead_party:
            result.append(row["raid"])
    return result


def membership_label(now, row):
    time_label = timeutil.membership_left_label(now, row["expires_at"])
    if row["lead"]:
        return "lead, {}".format(time_label)
    return time_label


def active_raids_grouped(conn, now):
    rows = conn.execute("SELECT * FROM raid_members ORDER BY raid ASC, party ASC").fetchall()
    by_raid = {}
    for row in rows:
        if timeutil.is_expired(now, row["expires_at"]):
            continue
        by_raid.setdefault(row["raid"], []).append(row)
    return by_raid


def list_raids(ctx):
    by_raid = active_raids_grouped(ctx.conn, ctx.now)
    lines = []
    for raid_name in sorted(by_raid):
        lines.append("{}:".format(raid_name))
        for row in by_raid[raid_name]:
            lines.append("  {} ({})".format(row["party"], membership_label(ctx.now, row)))
    return lines
