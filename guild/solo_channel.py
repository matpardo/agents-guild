from guild import events, solo_players

MESSAGE_MAX_LENGTH = 300
BOARD_LIMIT = 20


def post(ctx_conn, now, origin, session_id, project, player, text):
    payload = {"repo": player["repo"], "job": player["job"], "text": text}
    events.record(ctx_conn, now, origin, None, session_id, project, "solo.message", "guild", payload)


def _names_by_health_job(projects_by_name):
    names = {}
    for project_data in projects_by_name.values():
        for player in project_data.get("solo_players", []):
            health_job = solo_players.health_job_name(player["repo"], player["job"])
            names[health_job] = (solo_players.player_name(player), solo_players.JOBS[player["job"]]["class"])
    return names


def latest(conn, projects_by_name, limit):
    names = _names_by_health_job(projects_by_name)
    rows = conn.execute("SELECT health_job, ts, text FROM solo_messages ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    result = []
    for row in rows:
        name, job_class = names.get(row["health_job"], (row["health_job"], ""))
        result.append({"ts": row["ts"], "name": name, "class": job_class, "text": row["text"]})
    return result
