from guild import config, sanitize, timeutil
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
    latest = conn.execute(
        "SELECT done_at, pending FROM adventurers WHERE project = ? AND health_job = ?"
        " AND state IN ('done', 'dismissed') ORDER BY done_at DESC, id DESC LIMIT 1",
        (project, job["name"]),
    ).fetchone()
    last_done = None if latest is None else latest["done_at"]
    pending = (
        None if latest is None or latest["pending"] is None else sanitize.strip_control_sequences(latest["pending"])
    )
    if running is not None:
        return "running", last_done, pending
    if last_done is None:
        return "due", None, None
    if now - timeutil.from_iso(last_done) >= timeutil.parse_duration(job["every"]):
        return "due", last_done, pending
    return "ok", last_done, pending


def _open_asks(conn, project, job):
    rows = conn.execute(
        "SELECT asks.id, asks.question FROM asks JOIN adventurers ON asks.party = 'adventurer ' || adventurers.id"
        " WHERE asks.state = 'open' AND adventurers.project = ? AND adventurers.health_job = ? ORDER BY asks.id ASC",
        (project, job["name"]),
    ).fetchall()
    return [{"id": row["id"], "question": sanitize.strip_control_sequences(row["question"])} for row in rows]


def hero_label(project_data, job_name):
    if project_data is None:
        return None
    for job in project_data.get("health_jobs", []):
        if job["name"] == job_name and "hero" in job:
            return "{} ({})".format(job["hero"], job_name)
    return None


def models(ctx, projects_by_name):
    result = []
    for project in sorted(projects_by_name):
        for job in projects_by_name[project].get("health_jobs", []):
            state, last_done, pending = _state(ctx.conn, ctx.now, project, job)
            result.append(
                {
                    "project": project,
                    "name": job["name"],
                    "state": state,
                    "hero": job.get("hero"),
                    "last_done": last_done,
                    "pending": pending,
                    "asks": _open_asks(ctx.conn, project, job),
                    "every": job["every"],
                    "launch": LAUNCH_COMMAND.format(job["name"]),
                }
            )
    return result


def job_text(projects_dir, adventurer):
    if adventurer["health_job"] is None:
        return adventurer["job"]
    projects = {project["name"]: project for project in config.load_all_projects(projects_dir)}
    return hero_label(projects.get(adventurer["project"]), adventurer["health_job"]) or adventurer["job"]


def _title(model):
    if model["hero"] is None:
        return model["name"]
    return "{} ({})".format(model["hero"], model["name"])


def board_lines(models_, dim, wrap):
    lines = []
    for model in models_:
        line = "  {} \u2014 {}".format(_title(model), model["state"])
        if model["state"] == "due":
            line += " ({}, every {}) -> {}".format(model["project"], model["every"], model["launch"])
        else:
            line += " ({}, every {})".format(model["project"], model["every"])
        lines.append(line)
        if model["pending"] is not None:
            lines.extend(dim(text) for text in wrap("pending: {}".format(model["pending"]), "    "))
        for ask in model["asks"]:
            lines.extend(wrap("ask #{}: {}".format(ask["id"], ask["question"]), "    "))
    return lines
