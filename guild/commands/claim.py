from guild import config, db, events, identity, refs, timeutil
from guild.commands import quest as quest_commands
from guild.errors import GuildError

_TASK_AREA_PREFIX = "task:"


def _validate_area(area):
    if area.startswith(_TASK_AREA_PREFIX):
        refs.parse_task_ref(area[len(_TASK_AREA_PREFIX) :])


def _task_adventurer(ctx, project, area):
    if not area.startswith(_TASK_AREA_PREFIX):
        return None
    epic, tid = refs.parse_task_ref(area[len(_TASK_AREA_PREFIX) :])
    return quest_commands.adventurer_holder(ctx.conn, project, epic, tid)


def _task_open_quest(ctx, project, area):
    if not area.startswith(_TASK_AREA_PREFIX):
        return None
    epic, tid = refs.parse_task_ref(area[len(_TASK_AREA_PREFIX) :])
    return quest_commands.open_quest_holder(ctx.conn, project, epic, tid)


def claim(ctx, area, ttl, agent_type):
    _validate_area(area)
    binding = identity.require_binding(ctx.conn, ctx.session_id)
    project = config.require_project(ctx.cwd, ctx.projects_dir)
    adventurer_id = _task_adventurer(ctx, project, area)
    if adventurer_id is not None:
        raise GuildError("area '{}' is held by adventurer {}".format(area, adventurer_id), 1)
    open_slug = _task_open_quest(ctx, project, area)
    if open_slug is not None:
        raise GuildError("area '{}' is in open quest {}".format(area, open_slug), 1)
    row = ctx.conn.execute(
        "SELECT party, expires_at FROM claims WHERE project = ? AND area = ?", (project, area)
    ).fetchone()
    if row is not None and not timeutil.is_expired(ctx.now, row["expires_at"]):
        if row["party"] != binding["party"]:
            raise GuildError(
                "area '{}' is claimed by party '{}' until {}".format(area, row["party"], row["expires_at"]),
                1,
            )
    expires_at = timeutil.expires_at_iso(ctx.now, ttl)
    payload = {"project": project, "area": area, "party": binding["party"], "expires_at": expires_at}
    if agent_type is not None:
        payload["claimed_by_agent"] = agent_type
    with db.writing(ctx.conn):
        events.record(
            ctx.conn,
            ctx.now,
            ctx.origin,
            binding["party"],
            ctx.session_id,
            project,
            "claim.created",
            "guild",
            payload,
        )
    return "area '{}' claimed until {}".format(area, expires_at)


def check(ctx, area):
    project = config.require_project(ctx.cwd, ctx.projects_dir)
    binding = identity.resolve_binding(ctx.conn, ctx.session_id)
    adventurer_id = _task_adventurer(ctx, project, area)
    if adventurer_id is not None:
        return "held by adventurer {}".format(adventurer_id), 1
    row = ctx.conn.execute(
        "SELECT party, expires_at FROM claims WHERE project = ? AND area = ?", (project, area)
    ).fetchone()
    if row is None or timeutil.is_expired(ctx.now, row["expires_at"]):
        return "free", 0
    clock = timeutil.clock_label(row["expires_at"])
    if binding is not None and row["party"] == binding["party"]:
        return "held by you until {}".format(clock), 0
    return "held by party {} until {}".format(row["party"], clock), 1


def release(ctx, area):
    binding = identity.require_binding(ctx.conn, ctx.session_id)
    project = config.require_project(ctx.cwd, ctx.projects_dir)
    row = ctx.conn.execute("SELECT party FROM claims WHERE project = ? AND area = ?", (project, area)).fetchone()
    if row is None or row["party"] != binding["party"]:
        raise GuildError("party '{}' does not hold claim on '{}'".format(binding["party"], area), 1)
    release_for_party(ctx, project, binding["party"], area)
    return "area '{}' released".format(area)


def list_claims(conn, now):
    rows = conn.execute("SELECT * FROM claims").fetchall()
    result = []
    for row in rows:
        if timeutil.is_expired(now, row["expires_at"]):
            continue
        result.append(row)
    return result


def held_areas(ctx, project, party):
    rows = ctx.conn.execute(
        "SELECT area, expires_at FROM claims WHERE project = ? AND party = ? AND area LIKE 'area:%'",
        (project, party),
    ).fetchall()
    return [row["area"] for row in rows if not timeutil.is_expired(ctx.now, row["expires_at"])]


def release_for_party(ctx, project, party, area):
    with db.writing(ctx.conn):
        events.record(
            ctx.conn,
            ctx.now,
            ctx.origin,
            party,
            ctx.session_id,
            project,
            "claim.released",
            "guild",
            {"project": project, "area": area},
        )
