from guild import db, events

_DUPLICATE = "duplicate"
_PLAN = "plan"
_DRY_RUN_MODE = "dry-run"
_REAL_MODE = "on"


class Verdict:
    def __init__(self, kind):
        self.kind = kind


def _already_decided(conn, trigger, mode):
    rows = conn.execute(
        "SELECT mode FROM dispatch_decisions WHERE project = ? AND key = ?", (trigger.project, trigger.key)
    ).fetchall()
    if mode == _REAL_MODE:
        return any(row["mode"] == _REAL_MODE for row in rows)
    return bool(rows)


def evaluate(ctx, trigger, mode):
    if _already_decided(ctx.conn, trigger, mode):
        return Verdict(_DUPLICATE)
    return Verdict(_PLAN)


def _record_decision(ctx, trigger, mode, outcome):
    with db.writing(ctx.conn):
        events.record(
            ctx.conn,
            ctx.now,
            ctx.origin,
            trigger.party,
            None,
            trigger.project,
            "dispatch.decided",
            "local",
            {
                "project": trigger.project,
                "rule": trigger.rule,
                "key": trigger.key,
                "mode": mode,
                "outcome": outcome,
                "party": trigger.party,
                "generation": None,
                "permission_mode": None,
                "subject": trigger.subject,
                "reason": None,
            },
        )


def execute(ctx, trigger, mode, verdict):
    if verdict.kind == _DUPLICATE:
        return None
    _record_decision(ctx, trigger, mode, "planned")
    return "{}: {} {} -> planned: launch {}".format(trigger.project, trigger.rule, trigger.subject, trigger.party)


def dry_run_line(trigger, verdict):
    if verdict.kind == _DUPLICATE:
        return None
    return "{}: {} {} -> would plan launch {}".format(trigger.project, trigger.rule, trigger.subject, trigger.party)
