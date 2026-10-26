from guild import background, party_progress, sanitize, session_info, session_status, timeutil
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


def has_live_leader(ctx, party_row):
    if party_row["state"] == "awaiting-leader" or party_row["leader_session_id"] is None:
        return False
    return party_row["leader_session_id"] in session_info.live_session_ids(ctx.sessions_dir)


def _blocked_detail(groups):
    total = sum(len(group["tids"]) for group in groups)
    parts = ["{} — {}".format(len(group["tids"]), group["reason"] or "no reason") for group in groups]
    return "{} blocked: {}".format(total, "; ".join(parts))


def _offline_result(ctx, party_row):
    ask_since = _oldest_open_ask_since(ctx.conn, party_row["name"])
    if ask_since is not None:
        return _result("waiting-ask", ask_since, None)
    if party_row["parked"] is not None:
        return _result("parked", party_row["parked_at"], party_row["parked"])
    binding = {"party": party_row["name"], "project": party_row["project"]}
    if next_commands.has_work(ctx, binding):
        return _result("queued", None, None)
    groups = party_progress.blocked_groups(ctx.conn, party_row["name"])
    if groups:
        return _result("blocked", None, _blocked_detail(groups))
    return _result("idle", None, None)


def derive(ctx, party_row):
    if party_row["state"] == "closed":
        return _result("closed", None, None)
    if not has_live_leader(ctx, party_row):
        return _offline_result(ctx, party_row)
    session_row = session_status.current(ctx.conn, party_row["leader_session_id"])
    session_state = None if session_row is None else session_row["status"]
    if session_state == "waiting-permission":
        return _result("waiting-permission", session_row["since"], session_row["detail"])
    ask_since = _oldest_open_ask_since(ctx.conn, party_row["name"])
    if ask_since is not None and session_state != "working":
        return _result("waiting-ask", ask_since, None)
    if session_state in ("waiting-input", "stopped"):
        background_labels = background.labels(ctx.state_dir, party_row["leader_session_id"], ctx.now)
        if background_labels:
            return _result("waiting-background", session_row["since"], ", ".join(background_labels))
    if session_state == "waiting-input":
        return _result("waiting-input", session_row["since"], session_row["detail"])
    if session_state == "stopped":
        return _stopped_result(ctx, party_row, session_row)
    if session_row is None:
        return _result("unknown", None, None)
    return _result("working", session_row["since"], None)


def label(ctx, status):
    if status["since"] is None:
        return status["status"]
    return "{} {}".format(status["status"], timeutil.age_label(ctx.now, status["since"]))


def label_with_detail(ctx, status):
    text = label(ctx, status)
    if status["status"] not in ("parked", "blocked"):
        return text
    return "{} — {}".format(text, sanitize.strip_control_sequences(status["detail"]))
