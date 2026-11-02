from guild import config, db, events, identity, sanitize, session_info, solo_channel, solo_players, tmux_windows
from guild.commands import adventurer as adventurer_commands
from guild.errors import GuildError


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


def _require_known_project(ctx, project):
    if project is not None and project not in _projects_by_name(ctx):
        raise GuildError("unknown project '{}'".format(project), 1)


def _grouped_lines(items, format_item):
    groups = {}
    for item in items:
        groups.setdefault(item["project"], []).append(item)
    lines = []
    for project in sorted(groups):
        lines.append(project)
        lines.extend(format_item(item) for item in groups[project])
    return lines


def list_players(ctx, project):
    _require_known_project(ctx, project)
    rows = [row for row in _player_rows(ctx) if project is None or row["project"] == project]
    if not rows:
        return "no solo players"
    return "\n".join(_grouped_lines(rows, format_row))


def _find_player(project_data, repo, job_name):
    for player in project_data.get("solo_players", []):
        if player["repo"] == repo and player["job"] == job_name:
            return player
    return None


def _launch_player(ctx, project, project_data, repo, job_name, tmux):
    health_job = solo_players.health_job_name(repo, job_name)
    job = next(job for job in solo_players.jobs(project_data) if job["name"] == health_job)
    message = adventurer_commands.launch_window(project_data, job, _window_name(health_job), tmux)
    player = _find_player(project_data, repo, job_name)
    trigger = solo_players.current_trigger(ctx.conn, repo, job_name)
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
            {"repo": repo, "job": job_name, "trigger": trigger},
        )
        solo_channel.post(
            ctx.conn,
            ctx.now,
            ctx.origin,
            None,
            project,
            player,
            "{} ({}) started on {}: {}".format(
                solo_players.player_name(player), solo_players.JOBS[job_name]["class"], repo, trigger or "manual launch"
            ),
        )
    return message


def _window_name(health_job):
    return "solo-" + health_job


def _refuse_inside_session(ctx, command):
    if ctx.session_id is not None:
        raise GuildError("solo {} runs from the human terminal, not inside a Claude Code session".format(command), 1)


def _launch_row(ctx, row, tmux):
    if row["state"] == "running":
        raise GuildError("{} is running".format(row["name"]), 1)
    if row["state"] == "stalled":
        raise GuildError(
            "{} is stalled: run guild adventurer dismiss {}".format(row["name"], row["stalled_adventurer"]), 1
        )
    if tmux.installed() and _window_is_open(tmux, row["health_job"]):
        if not tmux_windows.kill_window(tmux, _window_name(row["health_job"])):
            raise GuildError("could not close its finished window", 1)
    project_data = config.load_project(ctx.projects_dir, row["project"])
    return _launch_player(ctx, row["project"], project_data, row["repo"], row["job"], tmux)


def _launch_line(ctx, row, tmux):
    if row["state"] == "running":
        return "{} skipped: running".format(row["name"])
    if row["state"] == "stalled":
        return "{} skipped: stalled, run guild adventurer dismiss {}".format(row["name"], row["stalled_adventurer"])
    try:
        _launch_row(ctx, row, tmux)
    except GuildError as error:
        return "{} not launched: {}".format(row["name"], error.message)
    return "{} launched".format(row["name"])


def _launch_all(ctx, project, tmux):
    _require_known_project(ctx, project)
    rows = [row for row in _player_rows(ctx) if project is None or row["project"] == project]
    if not rows:
        return "no solo players"
    return "\n".join(_launch_line(ctx, row, tmux) for row in rows)


def launch(ctx, repo, job_name, all_players, project, tmux):
    _refuse_inside_session(ctx, "launch")
    pair = repo is not None or job_name is not None
    if [pair, all_players, project is not None].count(True) != 1:
        raise GuildError("solo launch takes exactly one of '<repo> <job>', --all or --project <name>", 1)
    if all_players or project is not None:
        return _launch_all(ctx, project, tmux)
    if repo is None or job_name is None:
        raise GuildError("solo launch takes both '<repo>' and '<job>'", 1)
    current = config.require_project(ctx.cwd, ctx.projects_dir)
    project_data = config.load_project(ctx.projects_dir, current)
    if _find_player(project_data, repo, job_name) is None:
        raise GuildError("project '{}' has no solo player '{}' on '{}'".format(current, job_name, repo), 1)
    row = next(
        row for row in _player_rows(ctx) if row["project"] == current and (row["repo"], row["job"]) == (repo, job_name)
    )
    return _launch_row(ctx, row, tmux)


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
        try:
            lines.append(_launch_row(ctx, row, tmux))
        except GuildError as error:
            lines.append("solo player {} not launched: {}".format(row["name"], error.message))
    return "\n".join(lines)


def _solo_adventurer(ctx):
    adventurer = identity.resolve_adventurer(ctx.conn, ctx.session_id)
    if adventurer is None or adventurer["health_job"] is None:
        raise GuildError("solo say runs inside a solo player session", 1)
    project_data = config.load_project(ctx.projects_dir, adventurer["project"])
    player = solo_players.player_of_health_job(project_data, adventurer["health_job"])
    if player is None:
        raise GuildError("solo say runs inside a solo player session", 1)
    return adventurer, player


def say(ctx, text):
    adventurer, player = _solo_adventurer(ctx)
    clean = sanitize.strip_control_sequences(text).strip()
    if clean == "":
        raise GuildError("solo say text must not be empty", 1)
    if len(clean) > solo_channel.MESSAGE_MAX_LENGTH:
        raise GuildError("solo say text must be at most {} characters".format(solo_channel.MESSAGE_MAX_LENGTH), 1)
    with db.writing(ctx.conn):
        solo_channel.post(ctx.conn, ctx.now, ctx.origin, ctx.session_id, adventurer["project"], player, clean)
    return "posted"


def _projects_by_name(ctx):
    return {project["name"]: project for project in config.load_all_projects(ctx.projects_dir)}


def channel(ctx, limit, project):
    _require_known_project(ctx, project)
    messages = solo_channel.latest(ctx.conn, _projects_by_name(ctx), project, limit)
    if not messages:
        return "no messages"
    return "\n".join(
        _grouped_lines(messages, lambda m: "  {} {} [{}] {}".format(m["ts"], m["name"], m["class"], m["text"]))
    )


def _format_run(run):
    duration = "-" if run["duration"] is None else "{}s".format(run["duration"])
    return "  {} {} {} {}".format(run["started_at"], run["state"], duration, run["pending"] or "")


def runs(ctx, repo, job_name):
    for row in _player_rows(ctx):
        if row["repo"] == repo and row["job"] == job_name:
            return "\n".join(_format_run(run) for run in row["runs"]) or "no runs"
    raise GuildError("no solo player '{}' on '{}'".format(job_name, repo), 1)
