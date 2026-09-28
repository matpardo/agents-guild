def _guild_opinion(conn, project, epic, tid):
    rows = conn.execute(
        "SELECT quest_tasks.state AS state FROM quest_tasks"
        " JOIN quests ON quests.slug = quest_tasks.quest"
        " WHERE quests.project = ? AND quests.epic = ? AND quest_tasks.tid = ?",
        (project, epic, tid),
    ).fetchall()
    if not rows:
        return None
    return any(row["state"] == "done" for row in rows)


def _tracker_opinion(conn, project, epic, tid):
    row = conn.execute(
        "SELECT cards.status_category AS status_category FROM tasks"
        " JOIN cards ON cards.project = tasks.project AND cards.key = tasks.jira_key"
        " WHERE tasks.project = ? AND tasks.epic = ? AND tasks.tid = ?",
        (project, epic, tid),
    ).fetchone()
    if row is None:
        return None
    return row["status_category"] == "done"


def _sdd_opinion(conn, project, epic, tid):
    row = conn.execute(
        "SELECT sdd_status FROM tasks WHERE project = ? AND epic = ? AND tid = ?",
        (project, epic, tid),
    ).fetchone()
    if row is None:
        return None
    return row["sdd_status"] == "done"


_SOURCES = (
    ("guild", _guild_opinion),
    ("tracker", _tracker_opinion),
    ("sdd", _sdd_opinion),
)


def resolve_task_done(conn, project, epic, tid):
    opinions = []
    for name, opinion_fn in _SOURCES:
        opinion = opinion_fn(conn, project, epic, tid)
        if opinion is not None:
            opinions.append((name, opinion))

    disagreements = []
    if len({opinion for _, opinion in opinions}) > 1:
        disagreements = list(opinions)

    if not opinions:
        return False, None, disagreements
    deciding_source, deciding_opinion = opinions[0]
    return deciding_opinion, deciding_source, disagreements
