from guild import config, db, events, identity, names, refs
from guild.commands import notice as notice_commands
from guild.errors import GuildError

_NOTICE_TTL = "30d"


def _count(conn, project, finding_class):
    row = conn.execute(
        "SELECT COUNT(*) AS total FROM findings WHERE project = ? AND class = ?", (project, finding_class)
    ).fetchone()
    return row["total"]


def class_models(conn, project, threshold):
    rows = conn.execute(
        "SELECT class, COUNT(*) AS total FROM findings WHERE project = ?"
        " GROUP BY class ORDER BY total DESC, class ASC",
        (project,),
    ).fetchall()
    return [
        {
            "class": row["class"],
            "count": row["total"],
            "threshold": threshold,
            "at_threshold": threshold is not None and row["total"] >= threshold,
        }
        for row in rows
    ]


def list_classes(ctx):
    project = config.require_project(ctx.cwd, ctx.projects_dir)
    threshold = config.load_project(ctx.projects_dir, project).get("finding_guard_threshold")
    models = class_models(ctx.conn, project, threshold)
    if not models:
        return "no finding classes in {}".format(project)
    return "\n".join(
        "{}: {} PR(s){}".format(
            model["class"], model["count"], " (at threshold {})".format(threshold) if model["at_threshold"] else ""
        )
        for model in models
    )


def _announce_guard(ctx, party, project, finding_class, total):
    announces = "finding:{}:{}".format(project, finding_class)
    if notice_commands.announced(ctx.conn, announces):
        return
    text = "finding class {} repeated {} times in {}: make it an architecture guard".format(
        finding_class, total, project
    )
    notice_commands.create_announcing(ctx, party, text, "project:{}".format(project), _NOTICE_TTL, announces)


def record(ctx, ref, cls):
    names.validate_name(cls, "finding class")
    repo, number = refs.parse_pr_ref(ref)
    project = config.require_project(ctx.cwd, ctx.projects_dir)
    project_data = config.load_project(ctx.projects_dir, project)
    if repo not in project_data["github"]["repos"]:
        raise GuildError("repo '{}' is not in project '{}' github.repos".format(repo, project), 1)
    binding = identity.resolve_binding(ctx.conn, ctx.session_id)
    party = binding["party"] if binding is not None else None
    with db.writing(ctx.conn):
        events.record(
            ctx.conn,
            ctx.now,
            ctx.origin,
            party,
            ctx.session_id,
            project,
            "finding.recorded",
            "guild",
            {"project": project, "class": cls, "repo": repo, "number": number, "party": party},
        )
    total = _count(ctx.conn, project, cls)
    threshold = project_data.get("finding_guard_threshold")
    if threshold is not None and total >= threshold:
        _announce_guard(ctx, party, project, cls, total)
    return "finding class '{}' recorded: {} PR(s) in {}".format(cls, total, project)
