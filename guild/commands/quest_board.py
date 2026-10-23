from guild import config, resolve, timeutil
from guild.commands import quest as quest_commands

_HIDDEN_EPIC_STATUSES = ("done", "archived")


def _resolve_project(ctx, project):
    if project is None:
        return config.require_project(ctx.cwd, ctx.projects_dir)
    config.load_project(ctx.projects_dir, project)
    return project


def _task_line(conn, project, quest_row, task_row):
    line = "    {} {}".format(task_row["tid"], task_row["title"])
    adventurer_id = quest_commands.adventurer_holder(
        conn, project, quest_row["epic"] or quest_row["slug"], task_row["tid"]
    )
    if adventurer_id is None:
        return line
    return "{} (held by adventurer {})".format(line, adventurer_id)


def _open_quest_lines(conn, project):
    quests = conn.execute(
        "SELECT slug, epic, title FROM quests WHERE project = ? AND party IS NULL AND state = 'active'"
        " ORDER BY rowid ASC",
        (project,),
    ).fetchall()
    if not quests:
        return ["  none"]
    lines = []
    for quest_row in quests:
        scope = "epic {}".format(quest_row["epic"]) if quest_row["epic"] else "no epic"
        lines.append("  {} ({}): {}".format(quest_row["slug"], scope, quest_row["title"]))
        tasks = conn.execute(
            "SELECT tid, title FROM quest_tasks WHERE quest = ? ORDER BY tid", (quest_row["slug"],)
        ).fetchall()
        lines.extend(_task_line(conn, project, quest_row, task_row) for task_row in tasks)
    return lines


def _covered_tids(conn, project, epic):
    rows = conn.execute(
        "SELECT qt.tid AS tid FROM quest_tasks qt JOIN quests q ON q.slug = qt.quest"
        " WHERE q.project = ? AND q.epic = ?",
        (project, epic),
    ).fetchall()
    return {row["tid"] for row in rows}


def _claimed_tids(conn, now, project, epic):
    prefix = "task:{}/".format(epic)
    rows = conn.execute("SELECT area, expires_at FROM claims WHERE project = ?", (project,)).fetchall()
    return {
        row["area"][len(prefix):]
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
        if quest_commands.adventurer_holder(ctx.conn, project, epic, row["tid"]) is not None:
            continue
        if resolve.resolve_task_done(ctx.conn, project, epic, row["tid"])[0]:
            continue
        free.append(row)
    return free


def _free_task_lines(ctx, project):
    epics = ctx.conn.execute(
        "SELECT epic FROM epics WHERE project = ? AND COALESCE(sdd_status, '') NOT IN (?, ?) ORDER BY epic",
        (project,) + _HIDDEN_EPIC_STATUSES,
    ).fetchall()
    lines = []
    for epic_row in epics:
        free = _free_task_rows(ctx, project, epic_row["epic"])
        if not free:
            continue
        lines.append("  {}:".format(epic_row["epic"]))
        lines.extend("    {} {}".format(row["tid"], row["title"]) for row in free)
    return lines or ["  none"]


def board(ctx, project):
    name = _resolve_project(ctx, project)
    lines = ["project {}".format(name), "open quests:"]
    lines.extend(_open_quest_lines(ctx.conn, name))
    lines.append("free tasks:")
    lines.extend(_free_task_lines(ctx, name))
    return lines
