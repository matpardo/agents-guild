import json
from datetime import datetime

from guild import identity, merge_queue, paths, session_info, transcript_usage
from guild.commands import merge_queue as merge_queue_commands
from guild.commands import notice as notice_commands
from guild.commands import raid as raid_commands
from guild.commands import revive

_CHECKED_LIFECYCLES = ("draft", "converging", "ready")
_DRAFT_LIFECYCLES = ("draft", "converging")
_REASON_KINDS = (
    ("merge conflict", "conflict"),
    ("changes requested", "changes-requested"),
    ("unresolved", "threads"),
    ("behind base", "behind"),
)


def _wait(kind, subject, label):
    return {"kind": kind, "subject": subject, "label": label}


def _review_kinds(pr):
    reasons = merge_queue.review_reasons(
        pr["mergeable"], pr["review_decision"], pr["unresolved_threads"], pr["merge_state"]
    )
    return [(kind, reason) for reason in reasons for prefix, kind in _REASON_KINDS if prefix in reason]


def _real_failures(pr):
    if pr["checks_billing"]:
        return 0
    return pr["checks_failing"]


def _check_waits(pr):
    if pr["checks_pending"] > 0:
        return [_wait("checks-pending", pr["ref"], "checks pending ({})".format(pr["checks_pending"]))]
    if _real_failures(pr) > 0 and pr["lifecycle"] in _CHECKED_LIFECYCLES:
        return [_wait("checks-failing", pr["ref"], "checks failing ({})".format(pr["checks_failing"]))]
    return []


def _draft_green(pr):
    return (
        pr["lifecycle"] in _DRAFT_LIFECYCLES
        and _real_failures(pr) == 0
        and pr["checks_pending"] == 0
        and pr["checks_passing"] > 0
    )


def _pr_waits(ctx, pr, entry):
    waits = _check_waits(pr)
    review = _review_kinds(pr)
    waits.extend(_wait(kind, pr["ref"], reason) for kind, reason in review)
    if pr["needs_human_pr_review"]:
        waits.append(_wait("human-review", pr["ref"], "human review"))
    if _draft_green(pr) and not review and pr["blocked_external"] is None:
        waits.append(_wait("draft-green", pr["ref"], "green draft: mark ready"))
    if pr["lifecycle"] == "ready" and entry["state"] == "ready" and entry["external"] is None:
        waits.append(_wait("human-merge", pr["ref"], "merge"))
    return waits


def _party_prs(ctx, party_name):
    records = merge_queue_commands.open_pr_records(ctx.conn)
    if not any(pr["party"] == party_name for pr in records):
        return []
    entries = {
        entry["ref"]: entry
        for entry in merge_queue.compute(records, merge_queue_commands.load_pins(ctx.conn), [])["queue"]
    }
    return [(pr, entries[pr["ref"]]) for pr in records if pr["party"] == party_name]


def _ask_open_waits(ctx, party_name):
    rows = ctx.conn.execute(
        "SELECT id FROM asks WHERE party = ? AND state = 'open' ORDER BY id", (party_name,)
    ).fetchall()
    return [_wait("ask-open", "ask #{}".format(row["id"]), "ask #{} open".format(row["id"])) for row in rows]


def _cursor_seq(conn, session_id):
    row = conn.execute(
        "SELECT last_seq FROM cursors WHERE session_id = ?", (identity.cursor_key(session_id),)
    ).fetchone()
    if row is None:
        return 0
    return row["last_seq"]


def _unseen_waits(ctx, party_row):
    if party_row["leader_session_id"] is None:
        return []
    new_events = ctx.conn.execute(
        "SELECT kind, payload FROM events WHERE seq > ? AND kind IN ('ask.answered', 'notice.created')"
        " ORDER BY seq ASC",
        (_cursor_seq(ctx.conn, party_row["leader_session_id"]),),
    ).fetchall()
    name = party_row["name"]
    active_ids = {row["id"] for row in notice_commands.active_notices(ctx.conn, ctx.now)}
    raids = raid_commands.member_raid_names(ctx.conn, ctx.now, name)
    waits = []
    for event in new_events:
        payload = json.loads(event["payload"])
        if event["kind"] == "ask.answered":
            ask = ctx.conn.execute("SELECT party FROM asks WHERE id = ?", (payload["id"],)).fetchone()
            if ask is not None and ask["party"] == name:
                subject = "ask #{}".format(payload["id"])
                waits.append(_wait("ask-answered-unseen", subject, "{} answered".format(subject)))
        elif event["kind"] == "notice.created" and payload["party"] != name and payload["id"] in active_ids:
            if notice_commands.targeting([payload], party_row["project"], True, raids):
                subject = "notice #{}".format(payload["id"])
                waits.append(_wait("notices-unread", subject, "{} unread".format(subject)))
    return waits


def _limit_wait(ctx, party_row):
    if party_row["leader_session_id"] not in session_info.live_session_ids(ctx.sessions_dir):
        return []
    transcript = revive.find_transcript(paths.claude_projects_dir(), party_row["leader_session_id"])
    reset = None if transcript is None else transcript_usage.rate_limit_reset(transcript)
    if reset is None:
        return []
    if ctx.now.timestamp() < reset:
        return [_wait("limit-reset", party_row["name"], "resets {}".format(datetime.fromtimestamp(reset).strftime("%H:%M")))]
    return [_wait("limit-reset", party_row["name"], "reset: resume by hand")]


def for_party(ctx, party_row):
    if party_row["state"] == "closed":
        return []
    waits = []
    for pr, entry in _party_prs(ctx, party_row["name"]):
        waits.extend(_pr_waits(ctx, pr, entry))
    waits.extend(_ask_open_waits(ctx, party_row["name"]))
    waits.extend(_unseen_waits(ctx, party_row))
    waits.extend(_limit_wait(ctx, party_row))
    return waits
