from guild import config, resolve, task_holders, timeutil

_HIDDEN_EPIC_STATUSES = ("done", "archived")


def _resolve_project(ctx, project):
    if project is None:
        return config.require_project(ctx.cwd, ctx.projects_dir)
    config.load_project(ctx.projects_dir, project)
    return project


def _open_quest_models(conn, project):
    quests = conn.execute(
        "SELECT slug, epic, title, left_by, created_at, updated_at FROM quests"
        " WHERE project = ? AND party IS NULL AND state = 'active'"
        " ORDER BY rowid ASC",
        (project,),
    ).fetchall()
    models = []
    for quest_row in quests:
        tasks = conn.execute(
            "SELECT tid, title FROM quest_tasks WHERE quest = ? AND state != 'discarded' ORDER BY tid",
            (quest_row["slug"],),
        ).fetchall()
        models.append(
            {
                "slug": quest_row["slug"],
                "epic": quest_row["epic"],
                "title": quest_row["title"],
                "left_by": quest_row["left_by"],
                "dates": timeutil.dates_label(quest_row["created_at"], quest_row["updated_at"]),
                "tasks": [
                    {
                        "tid": task_row["tid"],
                        "title": task_row["title"],
                        "adventurer": task_holders.adventurer_holder(
                            conn, project, quest_row["epic"] or quest_row["slug"], task_row["tid"]
                        ),
                    }
                    for task_row in tasks
                ],
            }
        )
    return models


def _covered_tids(conn, project, epic):
    rows = conn.execute(
        "SELECT qt.tid AS tid FROM quest_tasks qt JOIN quests q ON q.slug = qt.quest"
        " WHERE q.project = ? AND q.epic = ? AND qt.state != 'discarded'",
        (project, epic),
    ).fetchall()
    return {row["tid"] for row in rows}


def _claimed_tids(conn, now, project, epic):
    prefix = "task:{}/".format(epic)
    rows = conn.execute("SELECT area, expires_at FROM claims WHERE project = ?", (project,)).fetchall()
    return {
        row["area"][len(prefix) :]
        for row in rows
        if row["area"].startswith(prefix) and not timeutil.is_expired(now, row["expires_at"])
    }


def _free_task_rows(ctx, project, epic):
    covered = _covered_tids(ctx.conn, project, epic)
    claimed = _claimed_tids(ctx.conn, ctx.now, project, epic)
    rows = ctx.conn.execute(
        "SELECT tid, title FROM tasks WHERE project = ? AND epic = ? ORDER BY order_idx IS NULL, order_idx, tid",
        (project, epic),
    ).fetchall()
    free = []
    for row in rows:
        if row["tid"] in covered or row["tid"] in claimed:
            continue
        if task_holders.adventurer_holder(ctx.conn, project, epic, row["tid"]) is not None:
            continue
        if resolve.resolve_task_done(ctx.conn, project, epic, row["tid"])[0]:
            continue
        free.append(row)
    return free


def _free_task_models(ctx, project):
    epics = ctx.conn.execute(
        "SELECT epic FROM epics WHERE project = ? AND COALESCE(sdd_status, '') NOT IN (?, ?) ORDER BY epic",
        (project,) + _HIDDEN_EPIC_STATUSES,
    ).fetchall()
    models = []
    for epic_row in epics:
        free = _free_task_rows(ctx, project, epic_row["epic"])
        if free:
            models.append(
                {
                    "epic": epic_row["epic"],
                    "tasks": [{"tid": row["tid"], "title": row["title"]} for row in free],
                }
            )
    return models


def _active_party_names(conn, project):
    rows = conn.execute(
        "SELECT name FROM parties WHERE project = ? AND state = 'active' ORDER BY name", (project,)
    ).fetchall()
    return [row["name"] for row in rows]


def data(ctx, project):
    return {
        "open_quests": _open_quest_models(ctx.conn, project),
        "free_tasks": _free_task_models(ctx, project),
        "parties": _active_party_names(ctx.conn, project),
    }


def _has_work(conn, project):
    row = conn.execute(
        "SELECT 1 FROM epics WHERE project = ? UNION ALL"
        " SELECT 1 FROM quests WHERE project = ? AND party IS NULL AND state = 'active' LIMIT 1",
        (project, project),
    ).fetchone()
    return row is not None


def models(ctx, project_names):
    return [dict(data(ctx, name), name=name) for name in sorted(project_names) if _has_work(ctx.conn, name)]


def _task_line(task):
    line = "    {} {}".format(task["tid"], task["title"])
    if task["adventurer"] is None:
        return line
    return "{} (held by adventurer {})".format(line, task["adventurer"])


def _dates_suffix(quest):
    if quest["dates"] is None:
        return ""
    return " · {}".format(quest["dates"])


def _details_suffix(quest):
    if quest["left_by"] is None:
        return _dates_suffix(quest)
    return "{} · left by {}".format(_dates_suffix(quest), quest["left_by"])


def _open_quest_lines(quests):
    if not quests:
        return ["  none"]
    lines = []
    for quest in quests:
        scope = "epic {}".format(quest["epic"]) if quest["epic"] else "no epic"
        lines.append("  {} ({}{}): {}".format(quest["slug"], scope, _details_suffix(quest), quest["title"]))
        lines.extend(_task_line(task) for task in quest["tasks"])
    return lines


def _free_task_lines(epics):
    lines = []
    for entry in epics:
        lines.append("  {}:".format(entry["epic"]))
        lines.extend("    {} {}".format(task["tid"], task["title"]) for task in entry["tasks"])
    return lines or ["  none"]


def summary_lines(model):
    lines = ["{} QUEST BOARD".format(model["name"])]
    for quest in model["open_quests"]:
        lines.append("  open quest {} ({} tasks{})".format(quest["slug"], len(quest["tasks"]), _details_suffix(quest)))
    for entry in model["free_tasks"]:
        lines.append("  free tasks {}: {}".format(entry["epic"], len(entry["tasks"])))
    if len(lines) == 1:
        lines.append("  none")
    return lines


def board(ctx, project):
    name = _resolve_project(ctx, project)
    model = data(ctx, name)
    lines = ["project {}".format(name), "open quests:"]
    lines.extend(_open_quest_lines(model["open_quests"]))
    lines.append("free tasks:")
    lines.extend(_free_task_lines(model["free_tasks"]))
    return lines
