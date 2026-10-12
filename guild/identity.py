from guild.errors import GuildError

HUMAN_LABEL = "human"
UNBOUND_SESSION_LABEL = "unbound session"

UNBOUND_HINT = (
    "session not bound: continuing a party's work \u2192 `guild party resume <party>`;"
    " otherwise ask the human before `guild party start` or `guild quest add`"
    " (one-off changes stay unbound)"
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


def resolve_actor(conn, session_id):
    if session_id is None:
        return None, False
    binding = resolve_binding(conn, session_id)
    if binding is not None:
        return binding["party"], False
    return None, True


def actor_label(party, unbound):
    if party is not None:
        return party
    if unbound:
        return UNBOUND_SESSION_LABEL
    return HUMAN_LABEL
