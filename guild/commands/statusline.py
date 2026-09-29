from guild import identity
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
    if total_open_asks:
        parts.append("⚑{} asks".format(total_open_asks))
    if targeting:
        noun = "notice" if len(targeting) == 1 else "notices"
        parts.append("{} {}".format(len(targeting), noun))
    return " · ".join(parts)
