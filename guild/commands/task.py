from guild import db, events, identity
from guild.errors import GuildError


def _load_quest(ctx, quest):
    row = ctx.conn.execute(
        "SELECT slug, project, party, epic, state FROM quests WHERE slug = ?", (quest,)
    ).fetchone()
    if row is None:
        raise GuildError("unknown quest '{}'".format(quest), 1)
    return row


def _require_owner(binding, quest_row):
    if quest_row["party"] != binding["party"]:
        raise GuildError(
            "quest '{}' is owned by party '{}'".format(quest_row["slug"], quest_row["party"]), 1
        )


def _load_task(ctx, quest, tid):
    row = ctx.conn.execute(
        "SELECT quest, tid, state FROM quest_tasks WHERE quest = ? AND tid = ?", (quest, tid)
    ).fetchone()
    if row is None:
        raise GuildError("unknown task '{}/{}'".format(quest, tid), 1)
    return row


def add(ctx, quest, tid, title):
    quest_row = _load_quest(ctx, quest)
    if quest_row["epic"] is not None:
        raise GuildError(
            "quest '{}' is an epic quest; tasks come from `quest add --tasks`;"
            " for extra work use `quest add <slug> --followups-of {}`".format(quest, quest),
            1,
        )
    binding = identity.require_binding(ctx.conn, ctx.session_id)
    _require_owner(binding, quest_row)
    if quest_row["state"] != "active":
        raise GuildError("quest '{}' is done".format(quest), 1)
    existing = ctx.conn.execute(
        "SELECT tid FROM quest_tasks WHERE quest = ? AND tid = ?", (quest, tid)
    ).fetchone()
    if existing is not None:
        raise GuildError("task '{}/{}' already exists".format(quest, tid), 1)
    with db.writing(ctx.conn):
        events.record(
            ctx.conn,
            ctx.now,
            ctx.origin,
            binding["party"],
            ctx.session_id,
            quest_row["project"],
            "task.added",
            "local",
            {"quest": quest, "tid": tid, "title": title},
        )
    return "task '{}/{}' added".format(quest, tid)


def start(ctx, quest, tid, summary):
    quest_row = _load_quest(ctx, quest)
    binding = identity.require_binding(ctx.conn, ctx.session_id)
    _require_owner(binding, quest_row)
    task_row = _load_task(ctx, quest, tid)
    if task_row["state"] == "done":
        raise GuildError("task '{}/{}' is already done".format(quest, tid), 1)
    with db.writing(ctx.conn):
        events.record(
            ctx.conn,
            ctx.now,
            ctx.origin,
            binding["party"],
            ctx.session_id,
            quest_row["project"],
            "task.started",
            "local",
            {"quest": quest, "tid": tid, "summary": summary},
        )
    return "task '{}/{}' started".format(quest, tid)


def block(ctx, quest, tid, reason):
    quest_row = _load_quest(ctx, quest)
    binding = identity.require_binding(ctx.conn, ctx.session_id)
    _require_owner(binding, quest_row)
    task_row = _load_task(ctx, quest, tid)
    if task_row["state"] == "done":
        raise GuildError("task '{}/{}' is already done".format(quest, tid), 1)
    with db.writing(ctx.conn):
        events.record(
            ctx.conn,
            ctx.now,
            ctx.origin,
            binding["party"],
            ctx.session_id,
            quest_row["project"],
            "task.blocked",
            "local",
            {"quest": quest, "tid": tid, "reason": reason},
        )
    return "task '{}/{}' blocked".format(quest, tid)


def done(ctx, quest, tid, summary):
    quest_row = _load_quest(ctx, quest)
    binding = identity.require_binding(ctx.conn, ctx.session_id)
    _require_owner(binding, quest_row)
    task_row = _load_task(ctx, quest, tid)
    if task_row["state"] == "done":
        raise GuildError("task '{}/{}' is already done".format(quest, tid), 1)
    with db.writing(ctx.conn):
        events.record(
            ctx.conn,
            ctx.now,
            ctx.origin,
            binding["party"],
            ctx.session_id,
            quest_row["project"],
            "task.done",
            "local",
            {"quest": quest, "tid": tid, "summary": summary},
        )
    return "task '{}/{}' done".format(quest, tid)
