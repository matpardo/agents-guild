from guild import config, db, events, identity
from guild.errors import GuildError


def _resolve_epic_tasks(conn, project, epic, tasks_csv):
    epic_row = conn.execute(
        "SELECT epic FROM epics WHERE project = ? AND epic = ?", (project, epic)
    ).fetchone()
    if epic_row is None:
        raise GuildError(
            "epic '{}' was never synced: run `guild sync --source sdd`".format(epic), 1
        )
    tasks = []
    for tid in tasks_csv.split(","):
        tid = tid.strip()
        if not tid:
            continue
        task_row = conn.execute(
            "SELECT tid, title FROM tasks WHERE project = ? AND epic = ? AND tid = ?",
            (project, epic, tid),
        ).fetchone()
        if task_row is None:
            raise GuildError(
                "task '{}' not found in epic '{}': run `guild sync --source sdd`".format(tid, epic), 1
            )
        tasks.append({"tid": task_row["tid"], "title": task_row["title"]})
    return tasks


def add(ctx, slug, title, epic, tasks_csv, no_epic):
    if no_epic and (epic is not None or tasks_csv is not None):
        raise GuildError("--no-epic cannot be combined with --epic or --tasks", 1)
    if not no_epic and (epic is None or tasks_csv is None):
        raise GuildError("epic quests require --epic and --tasks, or pass --no-epic", 1)
    existing = ctx.conn.execute("SELECT slug FROM quests WHERE slug = ?", (slug,)).fetchone()
    if existing is not None:
        raise GuildError("quest '{}' already exists".format(slug), 1)
    binding = identity.require_binding(ctx.conn, ctx.session_id)
    project = config.require_project(ctx.cwd, ctx.projects_dir)
    tasks = []
    if not no_epic:
        tasks = _resolve_epic_tasks(ctx.conn, project, epic, tasks_csv)
    with db.writing(ctx.conn):
        events.record(
            ctx.conn,
            ctx.now,
            ctx.origin,
            binding["party"],
            ctx.session_id,
            project,
            "quest.added",
            "local",
            {
                "slug": slug,
                "project": project,
                "party": binding["party"],
                "epic": epic,
                "title": title,
                "tasks": tasks,
            },
        )
    return "quest '{}' added".format(slug)
