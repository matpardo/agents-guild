from guild import timeutil
from guild.errors import GuildError

TASK_CLAIM_PREFIX = "task:{}/"


def _quest_holders(conn, project, epic, party, allow_open_quests):
    party_filter = "(q.party IS NULL OR q.party != ?)"
    if allow_open_quests:
        party_filter = "(q.party IS NOT NULL AND q.party != ?)"
    rows = conn.execute(
        "SELECT q.slug AS slug, q.party AS party, qt.tid AS tid"
        " FROM quests q JOIN quest_tasks qt ON qt.quest = q.slug"
        " WHERE q.project = ? AND q.epic = ? AND q.state = 'active' AND " + party_filter + " ORDER BY q.slug, qt.tid",
        (project, epic, party),
    ).fetchall()
    holders = {}
    for row in rows:
        holders.setdefault(row["tid"], row)
    return holders


def _claim_holders(conn, now, project, epic, party):
    prefix = TASK_CLAIM_PREFIX.format(epic)
    rows = conn.execute(
        "SELECT area, party, expires_at FROM claims WHERE project = ? AND party != ?",
        (project, party),
    ).fetchall()
    holders = {}
    for row in rows:
        if not row["area"].startswith(prefix):
            continue
        if timeutil.is_expired(now, row["expires_at"]):
            continue
        holders[row["area"][len(prefix) :]] = row
    return holders


def adventurer_holder(conn, project, epic, tid):
    row = conn.execute(
        "SELECT id FROM adventurers WHERE project = ? AND task = ? AND state = 'active'",
        (project, "{}/{}".format(epic, tid)),
    ).fetchone()
    if row is None:
        return None
    return row["id"]


def task_adventurer(conn, quest_row, tid):
    return adventurer_holder(conn, quest_row["project"], quest_row["epic"] or quest_row["slug"], tid)


def open_quest_holder(conn, project, epic, tid):
    row = conn.execute(
        "SELECT q.slug AS slug FROM quests q JOIN quest_tasks qt ON qt.quest = q.slug"
        " WHERE q.project = ? AND q.party IS NULL AND q.state = 'active' AND qt.tid = ?"
        " AND (q.epic = ? OR (q.epic IS NULL AND q.slug = ?)) ORDER BY q.slug",
        (project, tid, epic, epic),
    ).fetchone()
    if row is None:
        return None
    return row["slug"]


def reject_taken_tasks(conn, now, project, epic, tasks, party, allow_open_quests):
    quest_holders = _quest_holders(conn, project, epic, party, allow_open_quests)
    claim_holders = _claim_holders(conn, now, project, epic, party)
    conflicts = []
    for task in tasks:
        tid = task["tid"]
        adventurer_id = adventurer_holder(conn, project, epic, tid)
        if adventurer_id is not None:
            conflicts.append("{} is held by adventurer {}".format(tid, adventurer_id))
            continue
        quest_holder = quest_holders.get(tid)
        if quest_holder is not None and quest_holder["party"] is None:
            conflicts.append("{} is in open quest {}".format(tid, quest_holder["slug"]))
            continue
        if quest_holder is not None:
            conflicts.append("{} is in quest {} of party {}".format(tid, quest_holder["slug"], quest_holder["party"]))
            continue
        claim_holder = claim_holders.get(tid)
        if claim_holder is not None:
            conflicts.append(
                "{} is claimed by party {} until {}".format(
                    tid, claim_holder["party"], timeutil.clock_label(claim_holder["expires_at"])
                )
            )
    if conflicts:
        raise GuildError("; ".join(conflicts), 1)
