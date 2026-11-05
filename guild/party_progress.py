def task_counts(conn, slug):
    rows = conn.execute("SELECT state FROM quest_tasks WHERE quest = ?", (slug,)).fetchall()
    states = [row["state"] for row in rows if row["state"] != "discarded"]
    return {
        "done": states.count("done"),
        "active": states.count("active"),
        "blocked": states.count("blocked"),
        "queued": states.count("queued"),
        "total": len(states),
    }


def _extra_pr_count(conn, party_name):
    return conn.execute(
        "SELECT COUNT(*) AS n FROM prs WHERE party = ? AND lifecycle NOT IN ('merged', 'closed') "
        "AND (task_quest IS NULL OR task_quest NOT IN "
        "(SELECT slug FROM quests WHERE party = ? AND state = 'active'))",
        (party_name, party_name),
    ).fetchone()["n"]


def remaining(conn, party_name):
    slugs = [
        row["slug"]
        for row in conn.execute(
            "SELECT slug FROM quests WHERE party = ? AND state = 'active' ORDER BY slug ASC", (party_name,)
        ).fetchall()
    ]
    counts = [task_counts(conn, slug) for slug in slugs]
    active = sum(count["active"] for count in counts)
    blocked = sum(count["blocked"] for count in counts)
    queued = sum(count["queued"] for count in counts)
    extra_prs = _extra_pr_count(conn, party_name)
    pending = active + blocked + queued
    return {
        "quests": [
            {"slug": slug, "done": count["done"], "total": count["total"]}
            for slug, count in zip(slugs, counts, strict=True)
        ],
        "active": active,
        "blocked": blocked,
        "queued": queued,
        "pending": pending,
        "extra_prs": extra_prs,
        "all_done": pending == 0 and extra_prs == 0,
    }


def blocked_groups(conn, party_name):
    rows = conn.execute(
        "SELECT t.quest, t.tid, t.blocked_reason FROM quest_tasks t JOIN quests q ON q.slug = t.quest"
        " WHERE q.party = ? AND q.state = 'active' AND t.state = 'blocked' ORDER BY t.quest ASC, t.tid ASC",
        (party_name,),
    ).fetchall()
    by_reason = {}
    for row in rows:
        by_reason.setdefault(row["blocked_reason"], []).append("{}/{}".format(row["quest"], row["tid"]))
    groups = [{"reason": reason, "tids": tids} for reason, tids in by_reason.items()]
    return sorted(groups, key=lambda group: (-len(group["tids"]), group["reason"] or ""))
