from guild import config, db, events, identity, pii, refs
from guild.commands import quest as quest_commands
from guild.errors import GuildError
from guild.ids import next_id

_RECENT_DONE_LIMIT = 10


def _require_free_session(conn, session_id):
    binding = identity.resolve_binding(conn, session_id)
    if binding is not None:
        raise GuildError(
            "session already leads party '{}': a session is a leader or an adventurer, never both".format(
                binding["party"]
            ),
            1,
        )
    adventurer = identity.resolve_adventurer(conn, session_id)
    if adventurer is not None:
        raise GuildError(
            "session is already an adventurer ({}): run `guild adventurer done --pending \"<text>\"`".format(
                adventurer["id"]
            ),
            1,
        )


def _require_task(conn, project, epic, tid):
    row = conn.execute(
        "SELECT tid FROM tasks WHERE project = ? AND epic = ? AND tid = ?", (project, epic, tid)
    ).fetchone()
    if row is None:
        raise GuildError(
            "task '{}/{}' not found: run `guild sync --source sdd`".format(epic, tid), 1
        )


def _validate_task(ctx, project, task):
    if task is None:
        return
    epic, tid = refs.parse_task_ref(task)
    _require_task(ctx.conn, project, epic, tid)
    quest_commands.reject_taken_tasks(ctx.conn, ctx.now, project, epic, [{"tid": tid}], "")


def _validate_text(ctx, project, name, value, limit):
    if value.strip() == "":
        raise GuildError("{} must not be empty".format(name), 1)
    pii.validate_field(value, name, limit, pii.project_patterns(ctx.projects_dir, project))


def start(ctx, job, task):
    if ctx.session_id is None:
        raise GuildError("adventurer start requires a Claude Code session", 1)
    _require_free_session(ctx.conn, ctx.session_id)
    project = config.require_project(ctx.cwd, ctx.projects_dir)
    _validate_text(ctx, project, "adventurer job", job, pii.ADVENTURER_JOB_MAX_LENGTH)
    _validate_task(ctx, project, task)
    adventurer_id = next_id(ctx.conn, "adventurers")
    with db.writing(ctx.conn):
        events.record(
            ctx.conn,
            ctx.now,
            ctx.origin,
            None,
            ctx.session_id,
            project,
            "adventurer.started",
            "local",
            {"id": adventurer_id, "job": job, "task": task},
        )
    return "adventurer {} started".format(adventurer_id)


def done(ctx, pending):
    adventurer = identity.resolve_adventurer(ctx.conn, ctx.session_id)
    if adventurer is None:
        raise GuildError("session is not an active adventurer", 1)
    _validate_text(ctx, adventurer["project"], "--pending", pending, pii.HANDOFF_FIELD_MAX_LENGTH)
    with db.writing(ctx.conn):
        events.record(
            ctx.conn,
            ctx.now,
            ctx.origin,
            None,
            ctx.session_id,
            adventurer["project"],
            "adventurer.done",
            "local",
            {"id": adventurer["id"], "pending": pending},
        )
    return "adventurer {} done".format(adventurer["id"])


def _list_line(row):
    parts = [row["project"], row["state"], row["task"] and "task " + row["task"]]
    line = "{} {} ({})".format(row["id"], row["job"], ", ".join(part for part in parts if part))
    if row["state"] == "done":
        line += " pending: {}".format(row["pending"])
    return line


def list_adventurers(ctx):
    active = ctx.conn.execute(
        "SELECT * FROM adventurers WHERE state = 'active' ORDER BY id ASC"
    ).fetchall()
    recent = ctx.conn.execute(
        "SELECT * FROM adventurers WHERE state = 'done' ORDER BY done_at DESC, id DESC LIMIT ?",
        (_RECENT_DONE_LIMIT,),
    ).fetchall()
    if not active and not recent:
        return ["no adventurers"]
    return [_list_line(row) for row in active + recent]


def show(ctx, adventurer_id):
    row = ctx.conn.execute("SELECT * FROM adventurers WHERE id = ?", (adventurer_id,)).fetchone()
    if row is None:
        raise GuildError("unknown adventurer {}".format(adventurer_id), 1)
    lines = ["adventurer {}: {}".format(row["id"], row["job"]), "state: {}".format(row["state"])]
    lines.append("project: {}".format(row["project"]))
    if row["task"] is not None:
        lines.append("task: {}".format(row["task"]))
    lines.append("started: {}".format(row["started_at"]))
    if row["state"] == "done":
        lines.append("done: {}".format(row["done_at"]))
        lines.append("pending: {}".format(row["pending"]))
    return lines
