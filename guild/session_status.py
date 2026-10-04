from guild import events, sanitize

_MESSAGE_LIMIT = 200


def current(conn, session_id):
    return conn.execute(
        "SELECT session_id, party, status, detail, since FROM session_status WHERE session_id = ?",
        (session_id,),
    ).fetchone()


def waiting_payload(wait, message):
    text = sanitize.strip_control_sequences(message or "")
    text = sanitize.collapse_to_single_line(text)
    return {"wait": wait, "message": text[:_MESSAGE_LIMIT]}


def record_change(ctx, binding, kind, payload):
    return events.record(
        ctx.conn,
        ctx.now,
        ctx.origin,
        binding["party"],
        ctx.session_id,
        binding["project"],
        kind,
        "local",
        payload,
    )


def is_change(conn, session_id, status):
    row = conn.execute(
        "SELECT status FROM session_status WHERE session_id = ?", (session_id,)
    ).fetchone()
    return row is None or row["status"] != status


def blocked_rows(conn, party_names):
    rows = conn.execute(
        "SELECT s.party, s.detail, s.since FROM session_status s"
        " JOIN parties p ON p.name = s.party AND p.leader_session_id = s.session_id"
        " WHERE s.status = 'waiting-permission' AND p.state = 'active'"
        " ORDER BY s.since ASC, s.party ASC"
    ).fetchall()
    if party_names is None:
        return rows
    return [row for row in rows if row["party"] in party_names]
