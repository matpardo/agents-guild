import json
import sqlite3
from datetime import timedelta

from guild import db, events, locking, paths, timeutil
from guild.errors import GuildError

_BACKUP_NAME = "guild.db.pre-compact"
_DEDUP_KINDS = ("epic.synced", "tracker.synced", "pr.synced")
_SNAPSHOT_KINDS = ("epic.synced", "tracker.synced")
_SNAPSHOTS_KEPT = 2
_SESSION_FILE_MAX_AGE_DAYS = 30
_SESSION_FILE_PATTERNS = ("ctx/*", "ctx-baseline/*", "background/*/*")


class ResourcePlan:
    def __init__(self, retention_days, cutoff, events_count, samples, machine):
        self.retention_days = retention_days
        self.cutoff = cutoff
        self.events_count = events_count
        self.samples = samples
        self.machine = machine


class Plan:
    def __init__(self, doomed, totals, resources, session_files):
        self.doomed = doomed
        self.totals = totals
        self.resources = resources
        self.session_files = session_files


class Result:
    def __init__(self, deleted_counts, bytes_before, bytes_after, backup_path, backup_bytes):
        self.deleted_counts = deleted_counts
        self.bytes_before = bytes_before
        self.bytes_after = bytes_after
        self.backup_path = backup_path
        self.backup_bytes = backup_bytes


def _pr_key(payload):
    return ("pr", payload["repo"], payload["number"])


def _pr_signature(payload):
    comparable = {name: value for name, value in payload.items() if name != "synced_at"}
    return json.dumps(comparable, sort_keys=True)


def _snapshot_key(kind, payload):
    if kind == "epic.synced":
        return (kind, payload["project"], payload["epic"])
    return (kind, payload["project"])


def _stream(conn):
    return conn.execute(
        "SELECT seq, kind, payload FROM events"
        " WHERE kind IN ('epic.synced', 'tracker.synced') OR (kind >= 'pr.' AND kind < 'pr/')"
        " ORDER BY seq ASC"
    )


def _dedup_plan(conn):
    doomed = {kind: [] for kind in _DEDUP_KINDS}
    totals = {kind: 0 for kind in _DEDUP_KINDS}
    runs = {}
    kept = {}
    for row in _stream(conn):
        kind = row["kind"]
        payload = json.loads(row["payload"])
        if kind in _SNAPSHOT_KINDS:
            totals[kind] += 1
            snapshots = kept.setdefault(_snapshot_key(kind, payload), [])
            snapshots.append(row["seq"])
            if len(snapshots) > _SNAPSHOTS_KEPT:
                doomed[kind].append(snapshots.pop(0))
            continue
        if kind not in _DEDUP_KINDS:
            if "repo" in payload and "number" in payload:
                runs.pop(_pr_key(payload), None)
            continue
        totals[kind] += 1
        key, signature = _pr_key(payload), _pr_signature(payload)
        run = runs.get(key)
        if run is None or run[0] != signature:
            runs[key] = [signature, 1, row["seq"]]
            continue
        if run[1] >= 2:
            doomed[kind].append(run[2])
        run[1] += 1
        run[2] = row["seq"]
    return doomed, totals


def _count(conn, statement, cutoff):
    return conn.execute(statement, (cutoff,)).fetchone()[0]


def _resource_plan(conn, now, retention_days):
    cutoff = timeutil.to_iso(now - timedelta(days=retention_days))
    return ResourcePlan(
        retention_days,
        cutoff,
        _count(conn, "SELECT COUNT(*) FROM events WHERE kind = 'resources.sampled' AND ts < ?", cutoff),
        _count(conn, "SELECT COUNT(*) FROM resource_samples WHERE ts < ?", cutoff),
        _count(conn, "SELECT COUNT(*) FROM resource_machine WHERE ts < ?", cutoff),
    )


def _stale_session_files(state_dir, now):
    cutoff = (now - timedelta(days=_SESSION_FILE_MAX_AGE_DAYS)).timestamp()
    return [
        path
        for pattern in _SESSION_FILE_PATTERNS
        for path in sorted(state_dir.glob(pattern))
        if path.is_file() and path.stat().st_mtime < cutoff
    ]


def plan(ctx, resource_retention_days):
    doomed, totals = _dedup_plan(ctx.conn)
    return Plan(
        doomed,
        totals,
        _resource_plan(ctx.conn, ctx.now, resource_retention_days),
        _stale_session_files(ctx.state_dir, ctx.now),
    )


def lock(ctx):
    return locking.try_lock(ctx.state_dir / "compact", "compact.lock")


def backup_path():
    return paths.data_dir() / _BACKUP_NAME


def _write_backup(conn):
    target = backup_path()
    try:
        target.unlink(missing_ok=True)
        destination = sqlite3.connect(str(target))
        try:
            conn.backup(destination)
        finally:
            destination.close()
        target.chmod(0o600)
        return target
    except (sqlite3.Error, OSError) as error:
        raise GuildError("compact aborted, backup to {} failed: {}".format(target, error), 1) from error


def _delete_seqs(conn, seqs):
    conn.executemany("DELETE FROM events WHERE seq = ?", [(seq,) for seq in seqs])


def _delete_resources(conn, resources):
    conn.execute("DELETE FROM events WHERE kind = 'resources.sampled' AND ts < ?", (resources.cutoff,))
    conn.execute("DELETE FROM resource_samples WHERE ts < ?", (resources.cutoff,))
    conn.execute("DELETE FROM resource_machine WHERE ts < ?", (resources.cutoff,))


def _delete_session_files(state_dir, session_files):
    for path in session_files:
        path.unlink(missing_ok=True)
    for directory in state_dir.glob("background/*"):
        if directory.is_dir() and not any(directory.iterdir()):
            directory.rmdir()


def _deleted_counts(compact_plan):
    counts = {kind: len(seqs) for kind, seqs in compact_plan.doomed.items()}
    counts["resources.sampled"] = compact_plan.resources.events_count
    return counts


def _db_bytes():
    return paths.db_path().stat().st_size


def _vacuum(conn):
    try:
        conn.execute("VACUUM")
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except sqlite3.OperationalError as error:
        raise GuildError("compact deleted rows but VACUUM failed (database locked?): {}".format(error), 1) from error


def apply(ctx, compact_plan):
    target = _write_backup(ctx.conn)
    counts = _deleted_counts(compact_plan)
    bytes_before = _db_bytes()
    with db.writing(ctx.conn):
        for seqs in compact_plan.doomed.values():
            _delete_seqs(ctx.conn, seqs)
        _delete_resources(ctx.conn, compact_plan.resources)
        events.record(
            ctx.conn,
            ctx.now,
            ctx.origin,
            None,
            None,
            None,
            "db.compacted",
            "local",
            {"deleted": counts, "bytes_before": bytes_before},
        )
    _vacuum(ctx.conn)
    _delete_session_files(ctx.state_dir, compact_plan.session_files)
    return Result(counts, bytes_before, _db_bytes(), target, target.stat().st_size)


def _human(size):
    return "{:.1f}M".format(size / 1000000)


def _dedup_line(kind, compact_plan, verb):
    return "{}: {} {} of {}".format(kind, verb, len(compact_plan.doomed[kind]), compact_plan.totals[kind])


def _resource_line(resources, verb):
    return "resources older than {}d: {} {} events, {} samples, {} machine rows".format(
        resources.retention_days, verb, resources.events_count, resources.samples, resources.machine
    )


def report_lines(compact_plan, dry_run):
    verb = "would delete" if dry_run else "deleted"
    title = "compact (dry-run)" if dry_run else "compact"
    lines = [title]
    lines.extend(_dedup_line(kind, compact_plan, verb) for kind in _DEDUP_KINDS)
    lines.append(_resource_line(compact_plan.resources, verb))
    lines.append(
        "session files older than {}d: {} {}".format(_SESSION_FILE_MAX_AGE_DAYS, verb, len(compact_plan.session_files))
    )
    return lines


def result_lines(result):
    return [
        "backup {} ({})".format(result.backup_path, _human(result.backup_bytes)),
        "db {} -> {}".format(_human(result.bytes_before), _human(result.bytes_after)),
    ]
