from guild import events, solo_players

MESSAGE_MAX_LENGTH = 300
BOARD_LIMIT = 20


def post(ctx_conn, now, origin, session_id, project, player, text):
    payload = {"repo": player["repo"], "job": player["job"], "text": text}
    events.record(ctx_conn, now, origin, None, session_id, project, "solo.message", "guild", payload)


def _names_by_health_job(projects_by_name):
    names = {}
    for project_name, project_data in projects_by_name.items():
        for player in project_data.get("solo_players", []):
            health_job = solo_players.health_job_name(player["repo"], player["job"])
            names[health_job] = (
                solo_players.player_name(player),
                solo_players.JOBS[player["job"]]["class"],
                project_name,
            )
    return names


def latest(conn, projects_by_name, project, limit):
    names = _names_by_health_job(projects_by_name)
    if project is not None:
        names = {health_job: entry for health_job, entry in names.items() if entry[2] == project}
    rows = conn.execute("SELECT health_job, ts, text FROM solo_messages ORDER BY id DESC").fetchall()
    result = []
    for row in rows:
        if project is not None and row["health_job"] not in names:
            continue
        name, job_class, owner = names.get(row["health_job"], (row["health_job"], "", ""))
        result.append({"ts": row["ts"], "name": name, "class": job_class, "project": owner, "text": row["text"]})
    return result[:limit]
