from guild import session_status, timeutil
from guild.commands import next as next_commands


def _result(status, since, detail):
    return {"status": status, "since": since, "detail": detail}


def _oldest_open_ask_since(conn, party):
    row = conn.execute(
        "SELECT created_at FROM asks WHERE party = ? AND state = 'open' ORDER BY id ASC LIMIT 1",
        (party,),
    ).fetchone()
    if row is None:
        return None
    return row["created_at"]


def _stopped_result(ctx, party_row, session_row):
    binding = {"party": party_row["name"], "project": party_row["project"]}
    if next_commands.has_work(ctx, binding):
        return _result("stopped-with-work", session_row["since"], None)
    return _result("done", session_row["since"], None)


def derive(ctx, party_row):
    if party_row["state"] == "closed":
        return _result("closed", None, None)
    if party_row["state"] == "awaiting-leader":
        return _result("awaiting-leader", None, None)
    session_row = None
    if party_row["leader_session_id"] is not None:
        session_row = session_status.current(ctx.conn, party_row["leader_session_id"])
    session_state = None if session_row is None else session_row["status"]
    if session_state == "waiting-permission":
        return _result("waiting-permission", session_row["since"], session_row["detail"])
    ask_since = _oldest_open_ask_since(ctx.conn, party_row["name"])
    if ask_since is not None and session_state != "working":
        return _result("waiting-ask", ask_since, None)
    if session_state == "waiting-input":
        return _result("waiting-input", session_row["since"], session_row["detail"])
    if session_state == "stopped":
        return _stopped_result(ctx, party_row, session_row)
    since = None if session_row is None else session_row["since"]
    return _result("working", since, None)


def label(ctx, status):
    if status["since"] is None:
        return status["status"]
    return "{} {}".format(status["status"], timeutil.age_label(ctx.now, status["since"]))
