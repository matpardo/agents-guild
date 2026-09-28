from guild import config, db, events, identity, refs, timeutil
from guild.errors import GuildError

_TASK_AREA_PREFIX = "task:"


def _validate_area(area):
    if area.startswith(_TASK_AREA_PREFIX):
        refs.parse_task_ref(area[len(_TASK_AREA_PREFIX):])


def claim(ctx, area, ttl):
    _validate_area(area)
    binding = identity.require_binding(ctx.conn, ctx.session_id)
    project = config.require_project(ctx.cwd, ctx.projects_dir)
    row = ctx.conn.execute(
        "SELECT party, expires_at FROM claims WHERE project = ? AND area = ?", (project, area)
    ).fetchone()
    if row is not None and not timeutil.is_expired(ctx.now, row["expires_at"]):
        if row["party"] != binding["party"]:
            raise GuildError(
                "area '{}' is claimed by party '{}' until {}".format(
                    area, row["party"], row["expires_at"]
                ),
                1,
            )
    expires_at = timeutil.expires_at_iso(ctx.now, ttl)
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
            {"project": project, "area": area, "party": binding["party"], "expires_at": expires_at},
        )
    return "area '{}' claimed until {}".format(area, expires_at)


def release(ctx, area):
    binding = identity.require_binding(ctx.conn, ctx.session_id)
    project = config.require_project(ctx.cwd, ctx.projects_dir)
    row = ctx.conn.execute(
        "SELECT party FROM claims WHERE project = ? AND area = ?", (project, area)
    ).fetchone()
    if row is None or row["party"] != binding["party"]:
        raise GuildError("party '{}' does not hold claim on '{}'".format(binding["party"], area), 1)
    with db.writing(ctx.conn):
        events.record(
            ctx.conn,
            ctx.now,
            ctx.origin,
            binding["party"],
            ctx.session_id,
            project,
            "claim.released",
            "guild",
            {"project": project, "area": area},
        )
    return "area '{}' released".format(area)


def list_claims(conn, now):
    rows = conn.execute("SELECT * FROM claims").fetchall()
    result = []
    for row in rows:
        if timeutil.is_expired(now, row["expires_at"]):
            continue
        result.append(row)
    return result
