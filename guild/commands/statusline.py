from guild import identity, session_status
from guild.commands import notice as notice_commands
from guild.commands import raid as raid_commands


def record_ctx(state_dir, session_id, pct):
    directory = state_dir / "ctx"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / session_id).write_text(str(pct))


def read_ctx(state_dir, session_id):
    path = state_dir / "ctx" / session_id
    if not path.is_file():
        return None
    try:
        return int(path.read_text().strip())
    except ValueError:
        return None


def _raid_label(ctx, row):
    if raid_commands.is_paused(ctx.conn, row["raid"]):
        return "{} ⏸".format(row["raid"])
    return row["raid"]


def _identity_parts(ctx, party, generation):
    raids = sorted(raid_commands.member_raids(ctx.conn, ctx.now, party), key=lambda row: row["raid"])
    parts = []
    if raids:
        parts.append("⚔ " + ", ".join(_raid_label(ctx, row) for row in raids))
    parts.append("g{}".format(generation))
    return parts


def render(ctx, session_id):
    binding = identity.resolve_binding(ctx.conn, session_id)
    project = binding["project"] if binding is not None else None
    party = binding["party"] if binding is not None else None
    total_open_asks = ctx.conn.execute(
        "SELECT COUNT(*) AS n FROM asks WHERE state = 'open'"
    ).fetchone()["n"]
    active = notice_commands.active_notices(ctx.conn, ctx.now)
    raid_member_of = raid_commands.member_raid_names(ctx.conn, ctx.now, party)
    targeting = notice_commands.targeting(active, project, True, raid_member_of)
    parts = []
    if party is not None:
        parts.extend(_identity_parts(ctx, party, binding["generation"]))
    if total_open_asks:
        parts.append("⚑{} asks".format(total_open_asks))
    if targeting:
        noun = "notice" if len(targeting) == 1 else "notices"
        parts.append("{} {}".format(len(targeting), noun))
    blocked = len(session_status.blocked_rows(ctx.conn, None))
    if blocked:
        parts.append("⏸{} blocked".format(blocked))
    return " · ".join(parts)
