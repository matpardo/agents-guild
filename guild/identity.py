from guild.errors import GuildError

UNBOUND_HINT = (
    "session not bound: run `guild party start <name>` or `guild party resume <party>`"
)


def resolve_binding(conn, session_id):
    if session_id is None:
        return None
    row = conn.execute(
        "SELECT name, project, generation FROM parties WHERE leader_session_id = ? AND state = 'active'",
        (session_id,),
    ).fetchone()
    if row is None:
        return None
    return {"party": row["name"], "project": row["project"], "generation": row["generation"]}


def require_binding(conn, session_id):
    binding = resolve_binding(conn, session_id)
    if binding is None:
        raise GuildError(UNBOUND_HINT, 1)
    return binding


def cursor_key(session_id):
    if session_id is None:
        return "human"
    return session_id
