import glob
import os
from pathlib import Path

from guild import config, db, events, health_jobs, identity, pii, refs, resume, tmux_windows
from guild.commands import quest as quest_commands
from guild.errors import GuildError
from guild.ids import next_id

_RECENT_DONE_LIMIT = 10


def _require_free_session(conn, session_id):
    binding = identity.resolve_binding(conn, session_id)
    if binding is not None:
        raise GuildError(
            "session already leads party '{}': a session is a leader or an adventurer, never both".format(
                binding["party"]
            ),
            1,
        )
    adventurer = identity.resolve_adventurer(conn, session_id)
    if adventurer is not None:
        raise GuildError(
            "session is already an adventurer ({}): run `guild adventurer done --pending \"<text>\"`".format(
                adventurer["id"]
            ),
            1,
        )


def _require_task(conn, project, epic, tid):
    row = conn.execute(
        "SELECT tid FROM tasks WHERE project = ? AND epic = ? AND tid = ?", (project, epic, tid)
    ).fetchone()
    if row is None:
        raise GuildError(
            "task '{}/{}' not found: run `guild sync --source sdd`".format(epic, tid), 1
        )


def _is_open_free_quest_task(conn, project, slug, tid):
    row = conn.execute(
        "SELECT 1 FROM quests q JOIN quest_tasks qt ON qt.quest = q.slug"
        " WHERE q.slug = ? AND q.project = ? AND q.party IS NULL AND q.state = 'active'"
        " AND q.epic IS NULL AND qt.tid = ?",
        (slug, project, tid),
    ).fetchone()
    return row is not None


def _validate_task(ctx, project, task):
    if task is None:
        return
    epic, tid = refs.parse_task_ref(task)
    if not _is_open_free_quest_task(ctx.conn, project, epic, tid):
        _require_task(ctx.conn, project, epic, tid)
    quest_commands.reject_taken_tasks(ctx.conn, ctx.now, project, epic, [{"tid": tid}], "", True)


def _validate_text(ctx, project, name, value, limit):
    if value.strip() == "":
        raise GuildError("{} must not be empty".format(name), 1)
    pii.validate_field(value, name, limit, pii.project_patterns(ctx.projects_dir, project))


def _resolve_start_job(job, task, health_job):
    if health_job is None:
        if job is None:
            raise GuildError("adventurer start requires a job text or --job <name>", 1)
        return job
    if job is not None or task is not None:
        raise GuildError("--job cannot be combined with a job text or --task", 1)
    return health_job


def start(ctx, job, task, health_job):
    if ctx.session_id is None:
        raise GuildError("adventurer start requires a Claude Code session", 1)
    job = _resolve_start_job(job, task, health_job)
    _require_free_session(ctx.conn, ctx.session_id)
    project = config.require_project(ctx.cwd, ctx.projects_dir)
    if health_job is not None:
        health_jobs.require_job(config.load_project(ctx.projects_dir, project), health_job)
    _validate_text(ctx, project, "adventurer job", job, pii.ADVENTURER_JOB_MAX_LENGTH)
    _validate_task(ctx, project, task)
    adventurer_id = next_id(ctx.conn, "adventurers")
    with db.writing(ctx.conn):
        events.record(
            ctx.conn,
            ctx.now,
            ctx.origin,
            None,
            ctx.session_id,
            project,
            "adventurer.started",
            "local",
            {"id": adventurer_id, "job": job, "task": task, "health_job": health_job},
        )
    return "adventurer {} started".format(adventurer_id)


def _first_path(project_data):
    pattern = os.path.expanduser(project_data["paths"][0])
    parts = []
    for part in Path(pattern).parts:
        if glob.has_magic(part):
            break
        parts.append(part)
    return str(Path(*parts))


def launch(ctx, job_name, tmux):
    if ctx.session_id is not None:
        raise GuildError("adventurer launch runs from the human terminal, not inside a Claude Code session", 1)
    project = config.require_project(ctx.cwd, ctx.projects_dir)
    project_data = config.load_project(ctx.projects_dir, project)
    job = health_jobs.require_job(project_data, job_name)
    cwd = _first_path(project_data)
    if not os.path.isdir(cwd):
        raise GuildError("project path '{}' does not exist".format(cwd), 1)
    if not tmux.installed():
        raise GuildError("tmux not found: install tmux (e.g. sudo apt install tmux)", 1)
    session_is_up = tmux_windows.session_exists(tmux)
    window_name = "health-" + job_name
    if session_is_up and window_name in tmux_windows.window_names(tmux):
        raise GuildError("window '{}' already exists".format(window_name), 1)
    command = resume.health_command(job_name, job["command"])
    window_id = tmux_windows.create_window(tmux, window_name, cwd, command, session_is_up)
    if window_id is None:
        raise GuildError("tmux could not create the window", 1)
    tmux_windows.pin_window_name(tmux, window_id)
    tmux_windows.set_session_options(tmux)
    return "launched {} in {}: tmux attach -t {}".format(job_name, cwd, tmux_windows.SESSION)


def done(ctx, pending):
    adventurer = identity.resolve_adventurer(ctx.conn, ctx.session_id)
    if adventurer is None:
        raise GuildError("session is not an active adventurer", 1)
    _validate_text(ctx, adventurer["project"], "--pending", pending, pii.HANDOFF_FIELD_MAX_LENGTH)
    with db.writing(ctx.conn):
        events.record(
            ctx.conn,
            ctx.now,
            ctx.origin,
            None,
            ctx.session_id,
            adventurer["project"],
            "adventurer.done",
            "local",
            {"id": adventurer["id"], "pending": pending},
        )
    return "adventurer {} done".format(adventurer["id"])


def dismiss(ctx, adventurer_id):
    row = ctx.conn.execute("SELECT project, state FROM adventurers WHERE id = ?", (adventurer_id,)).fetchone()
    if row is None:
        raise GuildError("unknown adventurer {}".format(adventurer_id), 1)
    if row["state"] != "done":
        raise GuildError("adventurer {} is {}, not done".format(adventurer_id, row["state"]), 1)
    with db.writing(ctx.conn):
        events.record(
            ctx.conn,
            ctx.now,
            ctx.origin,
            None,
            ctx.session_id,
            row["project"],
            "adventurer.dismissed",
            "local",
            {"id": adventurer_id},
        )
    return "adventurer {} dismissed".format(adventurer_id)


def _list_line(row):
    parts = [row["project"], row["state"], row["task"] and "task " + row["task"]]
    line = "{} {} ({})".format(row["id"], row["job"], ", ".join(part for part in parts if part))
    if row["state"] == "done":
        line += " pending: {}".format(row["pending"])
    return line


def list_adventurers(ctx):
    active = ctx.conn.execute(
        "SELECT * FROM adventurers WHERE state = 'active' ORDER BY id ASC"
    ).fetchall()
    recent = ctx.conn.execute(
        "SELECT * FROM adventurers WHERE state = 'done' ORDER BY done_at DESC, id DESC LIMIT ?",
        (_RECENT_DONE_LIMIT,),
    ).fetchall()
    if not active and not recent:
        return ["no adventurers"]
    return [_list_line(row) for row in active + recent]


def show(ctx, adventurer_id):
    row = ctx.conn.execute("SELECT * FROM adventurers WHERE id = ?", (adventurer_id,)).fetchone()
    if row is None:
        raise GuildError("unknown adventurer {}".format(adventurer_id), 1)
    lines = ["adventurer {}: {}".format(row["id"], row["job"]), "state: {}".format(row["state"])]
    lines.append("project: {}".format(row["project"]))
    if row["task"] is not None:
        lines.append("task: {}".format(row["task"]))
    lines.append("started: {}".format(row["started_at"]))
    if row["state"] == "done":
        lines.append("done: {}".format(row["done_at"]))
        lines.append("pending: {}".format(row["pending"]))
    return lines
