from guild import config, db, events, identity, names, timeutil
from guild.errors import GuildError

_TASK_CLAIM_PREFIX = "task:{}/"


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


def _quest_holders(conn, project, epic, party):
    rows = conn.execute(
        "SELECT q.slug AS slug, q.party AS party, qt.tid AS tid"
        " FROM quests q JOIN quest_tasks qt ON qt.quest = q.slug"
        " WHERE q.project = ? AND q.epic = ? AND q.state = 'active' AND q.party != ?"
        " ORDER BY q.slug, qt.tid",
        (project, epic, party),
    ).fetchall()
    holders = {}
    for row in rows:
        holders.setdefault(row["tid"], row)
    return holders


def _claim_holders(conn, now, project, epic, party):
    prefix = _TASK_CLAIM_PREFIX.format(epic)
    rows = conn.execute(
        "SELECT area, party, expires_at FROM claims WHERE project = ? AND party != ?",
        (project, party),
    ).fetchall()
    holders = {}
    for row in rows:
        if not row["area"].startswith(prefix):
            continue
        if timeutil.is_expired(now, row["expires_at"]):
            continue
        holders[row["area"][len(prefix):]] = row
    return holders


def _reject_taken_tasks(conn, now, project, epic, tasks, party):
    quest_holders = _quest_holders(conn, project, epic, party)
    claim_holders = _claim_holders(conn, now, project, epic, party)
    conflicts = []
    for task in tasks:
        tid = task["tid"]
        quest_holder = quest_holders.get(tid)
        if quest_holder is not None:
            conflicts.append(
                "{} is in quest {} of party {}".format(tid, quest_holder["slug"], quest_holder["party"])
            )
            continue
        claim_holder = claim_holders.get(tid)
        if claim_holder is not None:
            conflicts.append(
                "{} is claimed by party {} until {}".format(
                    tid, claim_holder["party"], timeutil.clock_label(claim_holder["expires_at"])
                )
            )
    if conflicts:
        raise GuildError("; ".join(conflicts), 1)


def done(ctx, slug):
    binding = identity.require_binding(ctx.conn, ctx.session_id)
    row = ctx.conn.execute("SELECT party, project, state FROM quests WHERE slug = ?", (slug,)).fetchone()
    if row is None:
        raise GuildError("unknown quest '{}'".format(slug), 1)
    if row["party"] != binding["party"]:
        raise GuildError(
            "quest '{}' is not owned by party '{}'".format(slug, binding["party"]), 1
        )
    if row["state"] != "active":
        raise GuildError("quest '{}' is already {}".format(slug, row["state"]), 1)
    with db.writing(ctx.conn):
        events.record(
            ctx.conn,
            ctx.now,
            ctx.origin,
            binding["party"],
            ctx.session_id,
            row["project"],
            "quest.done",
            "local",
            {"slug": slug},
        )
    return "quest '{}' done".format(slug)


def _split_csv(csv):
    return [item.strip() for item in csv.split(",") if item.strip()]


def _free_tasks(tasks_csv, titles_csv):
    tids = _split_csv(tasks_csv)
    if titles_csv is None:
        return [{"tid": tid, "title": tid} for tid in tids]
    titles = _split_csv(titles_csv)
    if len(titles) != len(tids):
        raise GuildError("--titles must have the same number of items as --tasks", 1)
    return [{"tid": tid, "title": task_title} for tid, task_title in zip(tids, titles)]


def add(ctx, slug, title, epic, tasks_csv, titles_csv, no_epic):
    names.validate_name(slug, "quest slug")
    if no_epic and epic is not None:
        raise GuildError("--no-epic cannot be combined with --epic", 1)
    if titles_csv is not None and (not no_epic or tasks_csv is None):
        raise GuildError("--titles requires --no-epic and --tasks", 1)
    if not no_epic and (epic is None or tasks_csv is None):
        raise GuildError("epic quests require --epic and --tasks, or pass --no-epic", 1)
    existing = ctx.conn.execute("SELECT slug FROM quests WHERE slug = ?", (slug,)).fetchone()
    if existing is not None:
        raise GuildError("quest '{}' already exists".format(slug), 1)
    binding = identity.require_binding(ctx.conn, ctx.session_id)
    project = config.require_project(ctx.cwd, ctx.projects_dir)
    tasks = []
    if no_epic and tasks_csv is not None:
        tasks = _free_tasks(tasks_csv, titles_csv)
    if not no_epic:
        tasks = _resolve_epic_tasks(ctx.conn, project, epic, tasks_csv)
        _reject_taken_tasks(ctx.conn, ctx.now, project, epic, tasks, binding["party"])
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
