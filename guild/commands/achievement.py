import json
import statistics

from guild import timeutil


def _percent(done, total):
    if total == 0:
        return 0
    return done * 100 // total


def _in_window(ts, started_at, done_at):
    moment = timeutil.from_iso(ts)
    return started_at <= moment <= done_at


def _event_payload(row):
    return json.loads(row["payload"])


def _quest_started_at(conn, slug):
    rows = conn.execute("SELECT ts, payload FROM events WHERE kind = 'quest.added' ORDER BY seq").fetchall()
    for row in rows:
        if _event_payload(row)["slug"] == slug:
            return row["ts"]
    raise ValueError("quest.added event not found for '{}'".format(slug))


def _blocked_events(conn, slug):
    rows = conn.execute("SELECT payload FROM events WHERE kind = 'task.blocked'").fetchall()
    return sum(1 for row in rows if _event_payload(row)["quest"] == slug)


def _done_tids(conn, slug):
    rows = conn.execute(
        "SELECT tid FROM quest_tasks WHERE quest = ? AND state = 'done' ORDER BY tid", (slug,)
    ).fetchall()
    return [row["tid"] for row in rows]


def _epic_progress(conn, project, epic):
    if epic is None:
        return None
    rows = conn.execute(
        "SELECT sdd_status FROM tasks WHERE project = ? AND epic = ?", (project, epic)
    ).fetchall()
    done = sum(1 for row in rows if row["sdd_status"] == "done")
    return {"done": done, "total": len(rows), "percent": _percent(done, len(rows))}


def _jira_cards_done(conn, project, epic):
    if epic is None:
        return []
    epic_row = conn.execute(
        "SELECT jira_key FROM epics WHERE project = ? AND epic = ?", (project, epic)
    ).fetchone()
    if epic_row is None or epic_row["jira_key"] is None:
        return []
    rows = conn.execute(
        "SELECT key FROM cards WHERE project = ? AND parent_key = ? AND status_category = 'done'"
        " ORDER BY key",
        (project, epic_row["jira_key"]),
    ).fetchall()
    return [row["key"] for row in rows]


def _prs_merged(conn, slug):
    rows = conn.execute(
        "SELECT repo, number FROM prs WHERE task_quest = ? AND lifecycle = 'merged' ORDER BY repo, number",
        (slug,),
    ).fetchall()
    return ["{}#{}".format(row["repo"], row["number"]) for row in rows]


def _handoffs(conn, party, started_at, done_at):
    rows = conn.execute(
        "SELECT ts FROM events WHERE kind = 'party.handed_off' AND party = ?", (party,)
    ).fetchall()
    return sum(1 for row in rows if _in_window(row["ts"], started_at, done_at))


def _sessions(conn, party, started_at, done_at):
    rows = conn.execute(
        "SELECT started_at, ended_at FROM leaders WHERE party = ?", (party,)
    ).fetchall()
    count = 0
    for row in rows:
        if timeutil.from_iso(row["started_at"]) > done_at:
            continue
        if row["ended_at"] is not None and timeutil.from_iso(row["ended_at"]) < started_at:
            continue
        count += 1
    return count


def _answered_at_by_ask(conn):
    rows = conn.execute("SELECT ts, payload FROM events WHERE kind = 'ask.answered' ORDER BY seq").fetchall()
    answered = {}
    for row in rows:
        answered.setdefault(_event_payload(row)["id"], timeutil.from_iso(row["ts"]))
    return answered


def _ask_metrics(conn, party, started_at, done_at):
    rows = conn.execute(
        "SELECT ts, payload FROM events WHERE kind = 'ask.created' AND party = ? ORDER BY seq", (party,)
    ).fetchall()
    answered_at = _answered_at_by_ask(conn)
    raised = 0
    durations = []
    for row in rows:
        if not _in_window(row["ts"], started_at, done_at):
            continue
        raised += 1
        answer_moment = answered_at.get(_event_payload(row)["id"])
        if answer_moment is None or answer_moment > done_at:
            continue
        durations.append((answer_moment - timeutil.from_iso(row["ts"])).total_seconds())
    median = statistics.median(durations) if durations else None
    return {"asks_raised": raised, "asks_answered": len(durations), "median_answer_seconds": median}


def build(conn, slug, done_at, drift_findings):
    quest = conn.execute(
        "SELECT project, party, epic, title FROM quests WHERE slug = ?", (slug,)
    ).fetchone()
    started_iso = _quest_started_at(conn, slug)
    started_at = timeutil.from_iso(started_iso)
    done_tids = _done_tids(conn, slug)
    snapshot = {
        "started_at": started_iso,
        "done_at": timeutil.to_iso(done_at),
        "party": quest["party"],
        "project": quest["project"],
        "epic": quest["epic"],
        "title": quest["title"],
        "tasks_done": len(done_tids),
        "tasks_blocked_events": _blocked_events(conn, slug),
        "sdd_tids": done_tids,
        "epic_progress": _epic_progress(conn, quest["project"], quest["epic"]),
        "jira_cards_done": _jira_cards_done(conn, quest["project"], quest["epic"]),
        "prs_merged": _prs_merged(conn, slug),
        "handoffs": _handoffs(conn, quest["party"], started_at, done_at),
        "sessions": _sessions(conn, quest["party"], started_at, done_at),
        "drift": list(drift_findings),
    }
    snapshot.update(_ask_metrics(conn, quest["party"], started_at, done_at))
    return snapshot
