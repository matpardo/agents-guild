import re
import stat
from datetime import timedelta
from pathlib import Path

from guild import config, db, events, locking, names, session_info, timeutil
from guild.errors import GuildError

_NO_RETENTION_REASON = "no handoff_retention_days configured"
_NO_REGISTRY_LINE = "markers kept: no session registry"
_MARKER_MIN_AGE_SECONDS = 86400
_MARKER_DIRS = ("ctx", "hints")
_MARKER_NAME_RE = re.compile(
    r"^(?:nudge-|resumed-|raid-warn-|raid-pause-|attended-|wrapup-)?"
    r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"
    r"(?:-g\d+|-[0-9a-f]{16})?$"
)


class ApplyResult:
    def __init__(self, deleted, skipped):
        self.deleted = deleted
        self.skipped = skipped


class Plan:
    def __init__(self, actions, kept_without_retention, markers_skipped):
        self.actions = actions
        self.kept_without_retention = kept_without_retention
        self.markers_skipped = markers_skipped


class Action:
    def __init__(self, kind, verb, label, path, reason, party, generation):
        self.kind = kind
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
    return Action("handoff", verb, label, path, detail, row["party"], row["generation"])


def _unreadable_close_action(row):
    path = Path(row["handoff_path"])
    return Action("handoff", "skip", str(path), path, "unreadable close timestamp", row["party"], row["generation"])


def _handoff_actions(ctx, handoffs_dir):
    actions = []
    kept_without_retention = 0
    for rows in _handoff_rows(ctx.conn).values():
        for row in rows[:-1]:
            reason = _superseded_reason(row)
            if reason is not None:
                actions.append(_verdict(handoffs_dir, row, reason))
        try:
            reason, kept = _latest_reason(ctx, rows[-1])
        except (ValueError, TypeError):
            actions.append(_unreadable_close_action(rows[-1]))
            continue
        kept_without_retention += 1 if kept else 0
        if reason is not None:
            actions.append(_verdict(handoffs_dir, rows[-1], reason))
    return actions, kept_without_retention


def _protected_session_ids(ctx):
    rows = ctx.conn.execute(
        "SELECT leader_session_id FROM parties WHERE state != 'closed' AND leader_session_id IS NOT NULL"
    ).fetchall()
    return session_info.running_session_ids(ctx.sessions_dir) | {row["leader_session_id"] for row in rows}


def _marker_entries(state_dir):
    for directory_name in _MARKER_DIRS:
        directory = state_dir / directory_name
        if not directory.is_dir():
            continue
        for entry in sorted(directory.iterdir()):
            if _MARKER_NAME_RE.match(entry.name) is not None:
                yield entry


def _marker_skip(entry, reason):
    return Action("marker", "skip", str(entry), entry, reason, None, None)


def _marker_action(ctx, state_dir, protected, entry):
    session_id = _MARKER_NAME_RE.match(entry.name).group(1)
    if session_id in protected:
        return None
    try:
        entry_stat = entry.lstat()
    except FileNotFoundError:
        return None
    except OSError as error:
        return _marker_skip(entry, str(error))
    if not stat.S_ISREG(entry_stat.st_mode):
        return None
    if ctx.now.timestamp() - entry_stat.st_mtime < _MARKER_MIN_AGE_SECONDS:
        return None
    try:
        names.ensure_within(entry, state_dir)
    except GuildError:
        return _marker_skip(entry, "outside state dir")
    label = "{}/{}".format(entry.parent.name, entry.name)
    return Action("marker", "delete", label, entry, "session not running", None, None)


def _marker_actions(ctx, state_dir):
    if not session_info.running_session_ids(ctx.sessions_dir):
        return [], True
    protected = _protected_session_ids(ctx)
    actions = [_marker_action(ctx, state_dir, protected, entry) for entry in _marker_entries(state_dir)]
    return [action for action in actions if action is not None], False


def plan(ctx, handoffs_dir, state_dir):
    handoff_actions, kept_without_retention = _handoff_actions(ctx, handoffs_dir)
    marker_actions, markers_skipped = _marker_actions(ctx, state_dir)
    return Plan(handoff_actions + marker_actions, kept_without_retention, markers_skipped)


def _record_pruned(ctx, action):
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
            {"party": action.party, "generation": action.generation, "file": action.path.name},
        )


def _apply_one(ctx, action):
    action.path.unlink(missing_ok=True)
    if action.kind == "handoff":
        _record_pruned(ctx, action)


def apply(ctx, actions):
    deleted = 0
    skipped = []
    for action in actions:
        if not action.is_delete():
            continue
        try:
            _apply_one(ctx, action)
        except OSError as error:
            skipped.append(Action(action.kind, "skip", str(action.path), action.path, str(error), None, None))
            continue
        deleted += 1 if action.kind == "handoff" else 0
    return ApplyResult(deleted, skipped)


def lock(ctx):
    return locking.try_lock(ctx.state_dir / "handoff-prune", "prune.lock")


def prune(ctx, handoffs_dir):
    with lock(ctx) as acquired:
        if not acquired:
            return None
        return apply(ctx, plan(ctx, handoffs_dir, ctx.state_dir).actions).deleted


def _count_of(actions, kind):
    return len([action for action in actions if action.kind == kind and action.is_delete()])


def report_lines(prune_plan, dry_run):
    actions = prune_plan.actions
    title = "handoff prune (dry-run)" if dry_run else "handoff prune"
    lines = ["{}: {} handoffs, {} markers".format(title, _count_of(actions, "handoff"), _count_of(actions, "marker"))]
    delete_verb = "would delete" if dry_run else "delete"
    for action in actions:
        if action.is_delete():
            lines.append("{} {} {}: {}".format(delete_verb, action.kind, action.label, action.reason))
            continue
        lines.append("skip {}: {}".format(action.label, action.reason))
    if prune_plan.markers_skipped:
        lines.append(_NO_REGISTRY_LINE)
    if prune_plan.kept_without_retention > 0:
        lines.append(
            "kept {} closed-party handoff(s): {}".format(prune_plan.kept_without_retention, _NO_RETENTION_REASON)
        )
    return lines
