from guild import config, solo_players
from guild.commands import adventurer as adventurer_commands
from guild.errors import GuildError


def _player_rows(ctx):
    projects_by_name = {project["name"]: project for project in config.load_all_projects(ctx.projects_dir)}
    return solo_players.models(ctx.conn, ctx.now, projects_by_name)


def format_row(row):
    return "  {} [{}] {} {} {} trigger: {} last done: {} last pending: {}".format(
        row["name"],
        row["class"],
        row["repo"],
        row["job"],
        row["state"],
        row["trigger"] or "none",
        row["last_done"] or "never",
        row["last_pending"] or "none",
    )


def list_players(ctx):
    rows = _player_rows(ctx)
    if not rows:
        return "no solo players"
    return "\n".join(format_row(row) for row in rows)


def launch(ctx, repo, job_name, tmux):
    if ctx.session_id is not None:
        raise GuildError("solo launch runs from the human terminal, not inside a Claude Code session", 1)
    project = config.require_project(ctx.cwd, ctx.projects_dir)
    project_data = config.load_project(ctx.projects_dir, project)
    for player in project_data.get("solo_players", []):
        if player["repo"] == repo and player["job"] == job_name:
            health_job = solo_players.health_job_name(repo, job_name)
            job = next(job for job in solo_players.jobs(project_data) if job["name"] == health_job)
            return adventurer_commands.launch_window(project_data, job, "solo-" + health_job, tmux)
    raise GuildError("project '{}' has no solo player '{}' on '{}'".format(project, job_name, repo), 1)
