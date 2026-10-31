def red_rows(conn):
    rows = conn.execute(
        "SELECT repo, source, reason, external FROM main_status WHERE red = 1 ORDER BY repo, source"
    ).fetchall()
    return [
        {
            "repo": row["repo"],
            "source": row["source"],
            "reason": row["reason"] or "no reason given",
            "external": row["external"],
        }
        for row in rows
    ]
