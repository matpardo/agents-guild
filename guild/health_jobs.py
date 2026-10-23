from guild import timeutil
from guild.errors import GuildError

LAUNCH_COMMAND = "guild adventurer launch {}"


def require_job(project_data, job_name):
    for job in project_data.get("health_jobs", []):
        if job["name"] == job_name:
            return job
    raise GuildError("project '{}' has no health job '{}'".format(project_data["name"], job_name), 1)


def _state(conn, now, project, job):
    running = conn.execute(
        "SELECT 1 FROM adventurers WHERE project = ? AND health_job = ? AND state = 'active'",
        (project, job["name"]),
    ).fetchone()
    last_done = conn.execute(
        "SELECT MAX(done_at) AS done_at FROM adventurers WHERE project = ? AND health_job = ?"
        " AND state IN ('done', 'dismissed')",
        (project, job["name"]),
    ).fetchone()["done_at"]
    if running is not None:
        return "running", last_done
    if last_done is None:
        return "due", None
    if now - timeutil.from_iso(last_done) >= timeutil.parse_duration(job["every"]):
        return "due", last_done
    return "ok", last_done


def models(ctx, projects_by_name):
    result = []
    for project in sorted(projects_by_name):
        for job in projects_by_name[project].get("health_jobs", []):
            state, last_done = _state(ctx.conn, ctx.now, project, job)
            result.append(
                {
                    "project": project,
                    "name": job["name"],
                    "state": state,
                    "last_done": last_done,
                    "every": job["every"],
                    "launch": LAUNCH_COMMAND.format(job["name"]),
                }
            )
    return result


def pending_lines(models_):
    return [
        "  {} {} ({}, every {}) -> {}".format(
            model["name"], model["state"], model["project"], model["every"], model["launch"]
        )
        if model["state"] == "due"
        else "  {} running ({}, every {})".format(model["name"], model["project"], model["every"])
        for model in models_
        if model["state"] != "ok"
    ]
