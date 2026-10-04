_CLOSED_LIFECYCLES = ("merged", "closed")


def pr_line(row):
    failing = row["checks_failing"] if row["checks_failing"] is not None else 0
    passing = row["checks_passing"] if row["checks_passing"] is not None else 0
    tid = row["task_tid"] or row["card"] or ""
    line = "{}#{} [{}] checks:✗{} ✓{}  {} {}".format(
        row["repo"], row["number"], row["lifecycle"], failing, passing, tid, row["what"]
    )
    if row["lifecycle"] in _CLOSED_LIFECYCLES:
        return line
    return "{} — waits: {}".format(line, row["waits"])


def quest_lanes(conn, quest_slug):
    rows = conn.execute(
        "SELECT * FROM quest_tasks WHERE quest = ? ORDER BY tid ASC", (quest_slug,)
    ).fetchall()
    lanes = {"active": [], "queued": [], "blocked": []}
    for row in rows:
        if row["state"] == "done":
            continue
        if row["state"] == "active":
            lanes["active"].append("{} ({})".format(row["tid"], row["summary"] or row["title"]))
        elif row["state"] == "blocked":
            lanes["blocked"].append("{} — {}".format(row["tid"], row["blocked_reason"]))
        else:
            lanes["queued"].append(row["tid"])
    return lanes
