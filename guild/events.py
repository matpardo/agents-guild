import json
import uuid

from guild import reducers, sanitize
from guild.timeutil import to_iso


def record(conn, now, origin, party, session_id, project, kind, visibility, payload):
    payload = sanitize.sanitize_payload(payload)
    event_id = str(uuid.uuid4())
    ts = to_iso(now)
    conn.execute(
        "INSERT INTO events (id, ts, origin, party, session_id, project, kind, visibility, payload)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (event_id, ts, origin, party, session_id, project, kind, visibility, json.dumps(payload)),
    )
    row = conn.execute("SELECT seq FROM events WHERE id = ?", (event_id,)).fetchone()
    event = {
        "seq": row["seq"],
        "id": event_id,
        "ts": ts,
        "origin": origin,
        "party": party,
        "session_id": session_id,
        "project": project,
        "kind": kind,
        "visibility": visibility,
        "payload": payload,
    }
    reducers.apply(conn, event)
    return event


def all_events(conn):
    rows = conn.execute("SELECT * FROM events ORDER BY seq ASC").fetchall()
    events = []
    for row in rows:
        events.append(
            {
                "seq": row["seq"],
                "id": row["id"],
                "ts": row["ts"],
                "origin": row["origin"],
                "party": row["party"],
                "session_id": row["session_id"],
                "project": row["project"],
                "kind": row["kind"],
                "visibility": row["visibility"],
                "payload": json.loads(row["payload"]),
            }
        )
    return events


def events_after(conn, seq):
    rows = conn.execute(
        "SELECT * FROM events WHERE seq > ? ORDER BY seq ASC", (seq,)
    ).fetchall()
    events = []
    for row in rows:
        events.append(
            {
                "seq": row["seq"],
                "id": row["id"],
                "ts": row["ts"],
                "origin": row["origin"],
                "party": row["party"],
                "session_id": row["session_id"],
                "project": row["project"],
                "kind": row["kind"],
                "visibility": row["visibility"],
                "payload": json.loads(row["payload"]),
            }
        )
    return events


def max_seq(conn):
    row = conn.execute("SELECT MAX(seq) AS max_seq FROM events").fetchone()
    return row["max_seq"] or 0
