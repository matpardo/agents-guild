from guild import identity
from guild.commands import notice as notice_commands


def render(ctx, session_id):
    binding = identity.resolve_binding(ctx.conn, session_id)
    project = binding["project"] if binding is not None else None
    total_open_asks = ctx.conn.execute(
        "SELECT COUNT(*) AS n FROM asks WHERE state = 'open'"
    ).fetchone()["n"]
    active = notice_commands.active_notices(ctx.conn, ctx.now)
    targeting = notice_commands.targeting(active, project, True)
    parts = []
    if total_open_asks:
        parts.append("⚑{} asks".format(total_open_asks))
    if targeting:
        noun = "notice" if len(targeting) == 1 else "notices"
        parts.append("{} {}".format(len(targeting), noun))
    return " · ".join(parts)
