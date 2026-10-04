import json
from datetime import timedelta, timezone

from guild import db, events, paths, timeutil, transcript_usage

_GRACE = timedelta(minutes=10)
_TASK_KINDS = ("task.started", "task.blocked", "task.done")
_USAGE_FIELDS = ("input", "cache_creation", "cache_read", "output")


def _session_id(path):
    if path.parent.name == "subagents":
        return path.parts[-3]
    return path.stem


def _transcripts(projects_dir):
    if not projects_dir.is_dir():
        return []
    return sorted(projects_dir.glob("*/*.jsonl")) + sorted(projects_dir.glob("*/*/subagents/*.jsonl"))


def _task_windows(conn):
    rows = conn.execute(
        "SELECT kind, ts, party, payload FROM events WHERE kind IN (?, ?, ?) AND party IS NOT NULL"
        " ORDER BY seq ASC",
        _TASK_KINDS,
    ).fetchall()
    open_starts = {}
    windows = {}
    for row in rows:
        payload = json.loads(row["payload"])
        moment = timeutil.from_iso(row["ts"])
        key = (row["party"], payload["quest"], payload["tid"])
        if row["kind"] == "task.started":
            open_starts.setdefault(key, moment)
            continue
        start = open_starts.pop(key, None)
        if start is None:
            continue
        windows.setdefault(row["party"], []).append((start, moment, key[1], key[2]))
    for key, start in open_starts.items():
        windows.setdefault(key[0], []).append((start, None, key[1], key[2]))
    return windows


def _task_for(windows, party, moment):
    best = None
    for start, end, quest, tid in windows.get(party, []):
        if start > moment or (end is not None and moment >= end):
            continue
        if best is None or start > best[0]:
            best = (start, quest, tid)
    if best is None:
        return "", ""
    return best[1], best[2]


def _binding_of(conn, session_id):
    row = conn.execute(
        "SELECT party, project FROM events WHERE session_id = ? AND party IS NOT NULL"
        " ORDER BY seq DESC LIMIT 1",
        (session_id,),
    ).fetchone()
    if row is None:
        return None, None
    return row["party"], row["project"]


def _aggregate(messages, windows, party):
    totals = {}
    for message in messages:
        day = message.timestamp.astimezone(timezone.utc).date().isoformat()
        quest, tid = _task_for(windows, party, message.timestamp)
        key = (day, message.model, quest, tid)
        current = totals.setdefault(key, [0, 0, 0, 0])
        for index, field in enumerate(_USAGE_FIELDS):
            current[index] += getattr(message, field)
    return totals


def _stored_offset(conn, path):
    row = conn.execute("SELECT offset FROM transcript_cursors WHERE path = ?", (str(path),)).fetchone()
    if row is None:
        return 0
    return row["offset"]


def _payload(key, counts):
    day, model, quest, tid = key
    return {
        "day": day,
        "model": model,
        "quest": quest,
        "tid": tid,
        "account": "",
        "input_tokens": counts[0],
        "cache_creation_tokens": counts[1],
        "cache_read_tokens": counts[2],
        "output_tokens": counts[3],
    }


def _collect_transcript(ctx, path, windows, bindings):
    session_id = _session_id(path)
    if session_id not in bindings:
        bindings[session_id] = _binding_of(ctx.conn, session_id)
    party, project = bindings[session_id]
    with db.writing(ctx.conn):
        offset = _stored_offset(ctx.conn, path)
        if path.stat().st_size < offset:
            offset = 0
        messages, next_offset = transcript_usage.scan(path, offset, ctx.now - _GRACE)
        for key, counts in sorted(_aggregate(messages, windows, party).items()):
            if not any(counts):
                continue
            events.record(
                ctx.conn,
                ctx.now,
                ctx.origin,
                party,
                session_id,
                project,
                "cost.sampled",
                "local",
                _payload(key, counts),
            )
        ctx.conn.execute(
            "INSERT OR REPLACE INTO transcript_cursors (path, offset) VALUES (?, ?)",
            (str(path), next_offset),
        )


def _known_offsets(conn):
    rows = conn.execute("SELECT path, offset FROM transcript_cursors").fetchall()
    return {row["path"]: row["offset"] for row in rows}


def collect(ctx):
    projects_dir = paths.claude_projects_dir()
    windows = _task_windows(ctx.conn)
    known_offsets = _known_offsets(ctx.conn)
    bindings = {}
    for path in _transcripts(projects_dir):
        try:
            if path.stat().st_size == known_offsets.get(str(path)):
                continue
            _collect_transcript(ctx, path, windows, bindings)
        except FileNotFoundError:
            continue
