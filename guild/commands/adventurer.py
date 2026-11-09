import glob
import os
from pathlib import Path

from guild import (
    config,
    db,
    events,
    final_report,
    health_jobs,
    identity,
    pii,
    refs,
    resume,
    session_info,
    solo_channel,
    solo_players,
    task_holders,
    timeutil,
    tmux_windows,
)
from guild.commands import party as party_commands
from guild.commands import sync as sync_commands
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
            'session is already an adventurer ({}): run `guild adventurer done --pending "<text>"`'.format(
                adventurer["id"]
            ),
            1,
        )


def _require_synced_epic(conn, project, epic):
    row = conn.execute("SELECT 1 FROM epics WHERE project = ? AND epic = ?", (project, epic)).fetchone()
    if row is None:
        raise GuildError(
            "epic '{}' was never synced: run `guild sync --source sdd`, or `guild quest add <slug> --open"
            ' --no-epic --title "..." --tasks T01 --titles "..."` and start with --task <slug>/T01'.format(epic),
            1,
        )


def _is_open_free_quest_task(conn, project, slug, tid):
    row = conn.execute(
        "SELECT 1 FROM quests q JOIN quest_tasks qt ON qt.quest = q.slug"
        " WHERE q.slug = ? AND q.project = ? AND q.party IS NULL AND q.state = 'active'"
        " AND q.epic IS NULL AND qt.state != 'discarded' AND qt.tid = ?",
        (slug, project, tid),
    ).fetchone()
    return row is not None


def _validate_task(ctx, project, task):
    if task is None:
        return
    epic, tid = refs.parse_task_ref(task)
    if not _is_open_free_quest_task(ctx.conn, project, epic, tid):
        _require_synced_epic(ctx.conn, project, epic)
    task_holders.reject_taken_tasks(ctx.conn, ctx.now, project, epic, [{"tid": tid}], "", True)


def _validate_text(ctx, project, name, value, limit):
    if value.strip() == "":
        raise GuildError("{} must not be empty".format(name), 1)
    pii.validate_field(value, name, limit, pii.project_patterns(ctx.projects_dir, project))


def _resolve_start_job(job, task, health_job):
    if health_job is None:
        if job is None:
            raise GuildError("adventurer start requires a job text or --job <name>", 1)
        if task is None:
            raise GuildError(
                "adventurer start requires --task <epic>/<tid> (an SDD task, or a new one the PR adds to a synced"
                ' epic); without SDD run `guild quest add <slug> --open --no-epic --title "..." --tasks T01'
                ' --titles "..."` and pass --task <slug>/T01',
                1,
            )
        return job
    if job is not None or task is not None:
        raise GuildError("--job cannot be combined with a job text or --task", 1)
    return health_job


def start(ctx, job, task, health_job, reason):
    if ctx.session_id is None:
        raise GuildError("adventurer start requires a Claude Code session", 1)
    job = _resolve_start_job(job, task, health_job)
    _require_free_session(ctx.conn, ctx.session_id)
    project = config.require_project(ctx.cwd, ctx.projects_dir)
    if health_job is not None:
        health_jobs.require_job(config.load_project(ctx.projects_dir, project), health_job)
    _validate_text(ctx, project, "adventurer job", job, pii.ADVENTURER_JOB_MAX_LENGTH)
    pii.validate_reason(reason, ctx.projects_dir, project)
    with db.writing(ctx.conn):
        _validate_task(ctx, project, task)
        adventurer_id = next_id(ctx.conn, "adventurers")
        events.record(
            ctx.conn,
            ctx.now,
            ctx.origin,
            None,
            ctx.session_id,
            project,
            "adventurer.started",
            "local",
            {"id": adventurer_id, "job": job, "task": task, "health_job": health_job, "reason": reason},
        )
    return "adventurer {} started".format(adventurer_id)


def first_path(project_data):
    pattern = os.path.expanduser(project_data["paths"][0])
    parts = []
    for part in Path(pattern).parts:
        if glob.has_magic(part):
            break
        parts.append(part)
    return str(Path(*parts))


def launch_window(ctx, project, cwd, job, window_name, tmux):
    if not os.path.isdir(cwd):
        raise GuildError("project path '{}' does not exist".format(cwd), 1)
    if not tmux.installed():
        raise GuildError("tmux not found: install tmux (e.g. sudo apt install tmux)", 1)
    session_is_up = tmux_windows.session_exists(tmux)
    if session_is_up and window_name in tmux_windows.window_names(tmux):
        raise GuildError("window '{}' already exists".format(window_name), 1)
    command = resume.health_command(job["name"], job["command"])
    window_id = tmux_windows.create_window(tmux, window_name, cwd, command, session_is_up)
    if window_id is None:
        raise GuildError("tmux could not create the window", 1)
    tmux_windows.pin_window_name(tmux, window_id)
    tmux_windows.set_session_options(tmux)
    with db.writing(ctx.conn):
        events.record(
            ctx.conn,
            ctx.now,
            ctx.origin,
            None,
            None,
            project,
            "health_window.launched",
            "local",
            {"window_id": window_id},
        )
    return "launched {} in {}: tmux attach -t {}".format(job["name"], cwd, tmux_windows.SESSION)


def launch(ctx, job_name, tmux):
    if ctx.session_id is not None:
        raise GuildError("adventurer launch runs from the human terminal, not inside a Claude Code session", 1)
    project = config.require_project(ctx.cwd, ctx.projects_dir)
    project_data = config.load_project(ctx.projects_dir, project)
    job = health_jobs.require_job(project_data, job_name)
    return launch_window(ctx, project, first_path(project_data), job, "health-" + job_name, tmux)


def _post_solo_finished(ctx, adventurer, pending):
    if adventurer["health_job"] is None:
        return
    project_data = config.load_project(ctx.projects_dir, adventurer["project"])
    player = solo_players.player_of_health_job(project_data, adventurer["health_job"])
    if player is None:
        return
    text = "{} finished: {}".format(solo_players.player_name(player), pending)
    solo_channel.post(ctx.conn, ctx.now, ctx.origin, ctx.session_id, adventurer["project"], player, text)


def done(ctx, pending, lifecycle_runner):
    adventurer = identity.resolve_adventurer(ctx.conn, ctx.session_id)
    if adventurer is None:
        raise GuildError("session is not an active adventurer", 1)
    _validate_text(ctx, adventurer["project"], "--pending", pending, pii.HANDOFF_FIELD_MAX_LENGTH)
    open_prs = ctx.conn.execute(
        "SELECT repo, number FROM prs WHERE adventurer = ? AND lifecycle NOT IN ('merged', 'closed')"
        " ORDER BY repo ASC, number ASC",
        (adventurer["id"],),
    ).fetchall()
    stale = bool(sync_commands.refresh_prs(ctx, open_prs, lifecycle_runner))
    with db.writing(ctx.conn):
        if identity.resolve_adventurer(ctx.conn, ctx.session_id) is None:
            raise GuildError("session is not an active adventurer", 1)
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
        _post_solo_finished(ctx, adventurer, pending)
    lines = ["adventurer {} done".format(adventurer["id"]), final_report.adventurer_report(ctx, adventurer, pending)]
    if stale:
        lines.append(final_report.STALE_PR_NOTE)
    return "\n".join(lines)


def promote(ctx, name, reason, goal, done_when):
    adventurer = identity.resolve_adventurer(ctx.conn, ctx.session_id)
    if adventurer is None:
        raise GuildError("session is not an active adventurer", 1)
    party_commands.require_new_name(ctx.conn, name)
    pii.validate_reason(reason, ctx.projects_dir, adventurer["project"])
    party_commands.validate_goal_field(goal, "--goal", ctx.projects_dir, adventurer["project"])
    party_commands.validate_goal_field(done_when, "--done-when", ctx.projects_dir, adventurer["project"])
    with db.writing(ctx.conn):
        events.record(
            ctx.conn,
            ctx.now,
            ctx.origin,
            None,
            ctx.session_id,
            adventurer["project"],
            "adventurer.promoted",
            "local",
            {"id": adventurer["id"], "party": name},
        )
        party_commands.record_started(ctx, name, adventurer["project"], reason, goal, done_when, adventurer["id"])
    message = "adventurer {} promoted to party '{}', generation 1".format(adventurer["id"], name)
    if adventurer["task"] is None:
        return message
    return '{}\nadd task {} to a quest: `guild quest add <slug> --epic <epic> --tasks <tid> --reason "<text>"`'.format(
        message, adventurer["task"]
    )


def dismiss_stopped(ctx, project, adventurer_id):
    events.record(
        ctx.conn,
        ctx.now,
        ctx.origin,
        None,
        ctx.session_id,
        project,
        "adventurer.dismissed",
        "local",
        {"id": adventurer_id},
    )


def dismiss(ctx, adventurer_id):
    with db.writing(ctx.conn):
        row = ctx.conn.execute(
            "SELECT project, state, session_id FROM adventurers WHERE id = ?", (adventurer_id,)
        ).fetchone()
        if row is None:
            raise GuildError("unknown adventurer {}".format(adventurer_id), 1)
        if row["state"] == "active" and row["session_id"] in session_info.live_session_ids(ctx.sessions_dir):
            raise GuildError("adventurer {} is active and its session is alive".format(adventurer_id), 1)
        if row["state"] not in ("done", "active"):
            raise GuildError("adventurer {} is {}, not done".format(adventurer_id, row["state"]), 1)
        dismiss_stopped(ctx, row["project"], adventurer_id)
    return "adventurer {} dismissed".format(adventurer_id)


def _list_line(row):
    parts = [row["project"], row["state"], row["task"] and "task " + row["task"]]
    line = "{} {} ({})".format(row["id"], row["job"], ", ".join(part for part in parts if part))
    if row["state"] == "done":
        line += " pending: {}".format(row["pending"])
    return line


def list_adventurers(ctx):
    active = ctx.conn.execute("SELECT * FROM adventurers WHERE state = 'active' ORDER BY id ASC").fetchall()
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
    lines.append("started: {}".format(timeutil.issued_label(row["started_at"])))
    if row["reason"] is not None:
        lines.append("reason: {}".format(row["reason"]))
    if row["state"] == "done":
        lines.append("done: {}".format(timeutil.issued_label(row["done_at"])))
        lines.append("pending: {}".format(row["pending"]))
    return lines
