from guild import config, db, events, identity
from guild.errors import GuildError


def paused_repos(conn):
    return {row["repo"] for row in conn.execute("SELECT repo FROM base_pauses")}


def _owning_project(ctx, repo):
    for project in config.load_all_projects(ctx.projects_dir):
        if repo in project["github"]["repos"]:
            return project["name"]
    raise GuildError("repo '{}' is not in any project".format(repo), 1)


def _actor_party(ctx):
    if ctx.session_id is None:
        return None
    return identity.require_binding(ctx.conn, ctx.session_id)["party"]


def _append(ctx, kind, repo, project):
    events.record(
        ctx.conn,
        ctx.now,
        ctx.origin,
        _actor_party(ctx),
        ctx.session_id,
        project,
        kind,
        "local",
        {"repo": repo},
    )


def pause(ctx, repo):
    project = _owning_project(ctx, repo)
    with db.writing(ctx.conn):
        if repo in paused_repos(ctx.conn):
            raise GuildError("base of {} is already paused".format(repo), 1)
        _append(ctx, "base.paused", repo, project)
    return "base of {} paused".format(repo)


def resume(ctx, repo):
    project = _owning_project(ctx, repo)
    with db.writing(ctx.conn):
        if repo not in paused_repos(ctx.conn):
            raise GuildError("base of {} is not paused".format(repo), 1)
        _append(ctx, "base.resumed", repo, project)
    return "base of {} resumed".format(repo)
