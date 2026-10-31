from guild import config, db, events, identity
from guild.errors import GuildError


def _project_name(ctx, repo):
    for project in config.load_all_projects(ctx.projects_dir):
        if repo in project["github"]["repos"]:
            return project["name"]
    raise GuildError("repo '{}' does not belong to any configured project".format(repo), 1)


def _actor_party(ctx):
    binding = identity.resolve_binding(ctx.conn, ctx.session_id)
    if binding is None:
        return None
    return binding["party"]


def _record(ctx, repo, red, reason):
    project = _project_name(ctx, repo)
    with db.writing(ctx.conn):
        events.record(
            ctx.conn,
            ctx.now,
            ctx.origin,
            _actor_party(ctx),
            ctx.session_id,
            project,
            "main.marked",
            "guild",
            {"repo": repo, "red": red, "reason": reason},
        )


def red(ctx, repo, reason):
    if not reason.strip():
        raise GuildError("--reason must not be empty", 1)
    _record(ctx, repo, True, reason)
    return "marked main of '{}' red: {}".format(repo, reason)


def green(ctx, repo):
    _record(ctx, repo, False, None)
    return "cleared manual red mark on main of '{}'".format(repo)
