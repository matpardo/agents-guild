from guild import config, db, events, session_info, solo_players, tmux_windows
from guild.commands import adventurer as adventurer_commands
from guild.commands import notice as notice_commands
from guild.errors import GuildError

_LAUNCH_NOTICE_TTL = "2h"


def _player_rows(ctx):
    projects_by_name = {project["name"]: project for project in config.load_all_projects(ctx.projects_dir)}
    return solo_players.models(ctx.conn, ctx.now, projects_by_name, session_info.live_session_ids(ctx.sessions_dir))


def format_row(row):
    return "  {} [{}] {} {} {}{} trigger: {} last done: {} last pending: {}".format(
        row["name"],
        row["class"],
        row["repo"],
        row["job"],
        row["state"],
        solo_players.state_detail(row),
        row["trigger"] or "none",
        row["last_done"] or "never",
        row["last_pending"] or "none",
    )


def list_players(ctx):
    rows = _player_rows(ctx)
    if not rows:
        return "no solo players"
    return "\n".join(format_row(row) for row in rows)


def _find_player(project_data, repo, job_name):
    for player in project_data.get("solo_players", []):
        if player["repo"] == repo and player["job"] == job_name:
            return player
    return None


def _launch_player(ctx, project, project_data, repo, job_name, tmux):
    health_job = solo_players.health_job_name(repo, job_name)
    job = next(job for job in solo_players.jobs(project_data) if job["name"] == health_job)
    message = adventurer_commands.launch_window(project_data, job, _window_name(health_job), tmux)
    with db.writing(ctx.conn):
        events.record(
            ctx.conn,
            ctx.now,
            ctx.origin,
            None,
            None,
            project,
            "solo.launched",
            "guild",
            {"repo": repo, "job": job_name, "trigger": solo_players.current_trigger(ctx.conn, repo, job_name)},
        )
    return message


def _window_name(health_job):
    return "solo-" + health_job


def _refuse_inside_session(ctx, command):
    if ctx.session_id is not None:
        raise GuildError("solo {} runs from the human terminal, not inside a Claude Code session".format(command), 1)


def launch(ctx, repo, job_name, tmux):
    _refuse_inside_session(ctx, "launch")
    project = config.require_project(ctx.cwd, ctx.projects_dir)
    project_data = config.load_project(ctx.projects_dir, project)
    if _find_player(project_data, repo, job_name) is None:
        raise GuildError("project '{}' has no solo player '{}' on '{}'".format(project, job_name, repo), 1)
    return _launch_player(ctx, project, project_data, repo, job_name, tmux)


def _announce_launch(ctx, row):
    text = "solo player {} ({}) launched on {}: {}".format(row["name"], row["class"], row["repo"], row["trigger"])
    notice_commands.create_announcing(ctx, None, text, "project:" + row["project"], _LAUNCH_NOTICE_TTL, None)


def _window_is_open(tmux, health_job):
    if not tmux_windows.session_exists(tmux):
        return False
    return _window_name(health_job) in tmux_windows.window_names(tmux)


def tick(ctx, tmux):
    _refuse_inside_session(ctx, "tick")
    due = [row for row in _player_rows(ctx) if row["state"] == "due"]
    if not due:
        return ""
    if not tmux.installed():
        return "\n".join("solo player {} not launched: tmux not found".format(row["name"]) for row in due)
    lines = []
    for row in due:
        if _window_is_open(tmux, row["health_job"]):
            continue
        project_data = config.load_project(ctx.projects_dir, row["project"])
        try:
            lines.append(_launch_player(ctx, row["project"], project_data, row["repo"], row["job"], tmux))
        except GuildError as error:
            lines.append("solo player {} not launched: {}".format(row["name"], error.message))
            continue
        _announce_launch(ctx, row)
    return "\n".join(lines)
