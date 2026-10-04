from datetime import timedelta
from pathlib import Path

from guild import config, db, events, names, timeutil
from guild.errors import GuildError

_NO_RETENTION_REASON = "no handoff_retention_days configured"


class Action:
    def __init__(self, verb, label, path, reason, party, generation):
        self.verb = verb
        self.label = label
        self.path = path
        self.reason = reason
        self.party = party
        self.generation = generation

    def is_delete(self):
        return self.verb == "delete"


def _handoff_rows(conn):
    rows = conn.execute(
        "SELECT leaders.party AS party, leaders.generation AS generation, leaders.handoff_path AS handoff_path,"
        " leaders.handoff_consumed_at AS consumed_at, parties.state AS state, parties.project AS project"
        " FROM leaders JOIN parties ON parties.name = leaders.party"
        " WHERE leaders.handoff_path IS NOT NULL ORDER BY leaders.party ASC, leaders.generation ASC"
    ).fetchall()
    by_party = {}
    for row in rows:
        by_party.setdefault(row["party"], []).append(row)
    return by_party


def _closed_at(conn, party):
    row = conn.execute(
        "SELECT MAX(ts) AS ts FROM events WHERE kind = 'party.closed' AND party = ?", (party,)
    ).fetchone()
    if row["ts"] is None:
        return None
    return timeutil.from_iso(row["ts"])


def _retention_days(ctx, project):
    if project is None:
        return None
    try:
        return config.load_project(ctx.projects_dir, project).get("handoff_retention_days")
    except GuildError:
        return None


def _latest_reason(ctx, row):
    if row["state"] != "closed":
        return None, False
    days = _retention_days(ctx, row["project"])
    if days is None:
        return None, True
    closed_at = _closed_at(ctx.conn, row["party"])
    if closed_at is None or ctx.now < closed_at + timedelta(days=days):
        return None, False
    return "closed party, retention {}d expired".format(days), False


def _superseded_reason(row):
    if row["consumed_at"] is None:
        return None
    return "superseded and consumed"


def _verdict(handoffs_dir, row, reason):
    path = Path(row["handoff_path"])
    verb, detail = "delete", reason
    if path.is_symlink():
        verb, detail = "skip", "symlink"
    else:
        try:
            names.ensure_within(path, handoffs_dir)
        except GuildError:
            verb, detail = "skip", "outside handoffs dir"
    label = path.name if verb == "delete" else str(path)
    return Action(verb, label, path, detail, row["party"], row["generation"])


def plan(ctx, handoffs_dir):
    actions = []
    kept_without_retention = 0
    for rows in _handoff_rows(ctx.conn).values():
        for row in rows[:-1]:
            reason = _superseded_reason(row)
            if reason is not None:
                actions.append(_verdict(handoffs_dir, row, reason))
        reason, kept = _latest_reason(ctx, rows[-1])
        kept_without_retention += 1 if kept else 0
        if reason is not None:
            actions.append(_verdict(handoffs_dir, rows[-1], reason))
    return actions, kept_without_retention


def _apply_handoff(ctx, action):
    action.path.unlink(missing_ok=True)
    project = ctx.conn.execute("SELECT project FROM parties WHERE name = ?", (action.party,)).fetchone()["project"]
    with db.writing(ctx.conn):
        events.record(
            ctx.conn,
            ctx.now,
            ctx.origin,
            action.party,
            None,
            project,
            "handoff.pruned",
            "local",
            {"party": action.party, "generation": action.generation, "path": str(action.path)},
        )


def apply(ctx, actions):
    deleted = 0
    for action in actions:
        if not action.is_delete():
            continue
        _apply_handoff(ctx, action)
        deleted += 1
    return deleted


def report_lines(actions, dry_run, kept_without_retention):
    deletions = [action for action in actions if action.is_delete()]
    title = "handoff prune (dry-run)" if dry_run else "handoff prune"
    lines = ["{}: {} handoffs".format(title, len(deletions))]
    delete_verb = "would delete" if dry_run else "delete"
    for action in actions:
        if action.is_delete():
            lines.append("{} handoff {}: {}".format(delete_verb, action.label, action.reason))
            continue
        lines.append("skip {}: {}".format(action.label, action.reason))
    if kept_without_retention > 0:
        lines.append(
            "kept {} closed-party handoff(s): {}".format(kept_without_retention, _NO_RETENTION_REASON)
        )
    return lines
