from guild import db, events, identity, timeutil
from guild.commands import drift as drift_commands
from guild.commands import next as next_commands
from guild.commands import quest as quest_commands
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


def _with_sdd_hint(message, quest_row, hint_template, tid):
    if quest_row["epic"] is None:
        return message
    return "{}\n{}".format(message, hint_template.format(tid, quest_row["epic"]))


def add(ctx, quest, tid, title):
    quest_row = _load_quest(ctx, quest)
    binding = identity.require_binding(ctx.conn, ctx.session_id)
    _require_owner(binding, quest_row)
    if quest_row["state"] != "active":
        raise GuildError("quest '{}' is done".format(quest), 1)
    existing = ctx.conn.execute(
        "SELECT tid FROM quest_tasks WHERE quest = ? AND tid = ?", (quest, tid)
    ).fetchone()
    if existing is not None:
        raise GuildError("task '{}/{}' already exists".format(quest, tid), 1)
    if quest_row["epic"] is not None:
        quest_commands.reject_taken_tasks(
            ctx.conn, ctx.now, quest_row["project"], quest_row["epic"], [{"tid": tid}], binding["party"]
        )
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
    return _with_sdd_hint(
        "task '{}/{}' added".format(quest, tid), quest_row, "add {} to {} tasks.md in the SDD", tid
    )


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
    message = "task '{}/{}' started".format(quest, tid)
    card_key = drift_commands.started_card_to_move(ctx.conn, quest, tid)
    if card_key is None:
        return message
    return "{}\nmove {} to In Progress".format(message, card_key)


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
    return _with_sdd_hint(
        "task '{}/{}' done".format(quest, tid), quest_row, "mark {} done in {} tasks.md in the SDD", tid
    )


def _split_tids(tids_csv):
    tids = [tid.strip() for tid in tids_csv.split(",") if tid.strip()]
    if not tids:
        raise GuildError("no tasks to move", 1)
    if len(set(tids)) != len(tids):
        raise GuildError("duplicate task in the list", 1)
    return tids


def _require_move_target(source_row, target_row, target):
    if target_row is None:
        raise GuildError("unknown quest '{}'".format(target), 1)
    if target_row["slug"] == source_row["slug"]:
        raise GuildError("target quest is the source quest", 1)
    for row in (source_row, target_row):
        if row["state"] != "active":
            raise GuildError("quest '{}' is done".format(row["slug"]), 1)
    if target_row["project"] != source_row["project"]:
        raise GuildError("quest '{}' belongs to another project".format(target), 1)
    if target_row["epic"] != source_row["epic"]:
        raise GuildError("quest '{}' is in another epic".format(target), 1)


def _require_movable(ctx, quest_row, target, tid):
    task_row = _load_task(ctx, quest_row["slug"], tid)
    if task_row["state"] not in ("queued", "blocked"):
        raise GuildError("task '{}/{}' is {}: only queued or blocked tasks move".format(quest_row["slug"], tid, task_row["state"]), 1)
    taken = ctx.conn.execute(
        "SELECT tid FROM quest_tasks WHERE quest = ? AND tid = ?", (target, tid)
    ).fetchone()
    if taken is not None:
        raise GuildError("task '{}/{}' already exists".format(target, tid), 1)
    open_pr = ctx.conn.execute(
        "SELECT repo, number FROM prs WHERE task_quest = ? AND task_tid = ?"
        " AND COALESCE(gh_state, 'OPEN') = 'OPEN' AND lifecycle NOT IN ('merged', 'closed')",
        (quest_row["slug"], tid),
    ).fetchone()
    if open_pr is not None:
        raise GuildError("task '{}/{}' has open PR {}#{}".format(quest_row["slug"], tid, open_pr["repo"], open_pr["number"]), 1)
    area = next_commands.claim_area({"epic": quest_row["epic"], "quest": quest_row["slug"], "tid": tid})
    claim = ctx.conn.execute(
        "SELECT expires_at FROM claims WHERE project = ? AND area = ? AND party = ?",
        (quest_row["project"], area, quest_row["party"]),
    ).fetchone()
    if claim is not None and not timeutil.is_expired(ctx.now, claim["expires_at"]):
        raise GuildError("task '{}/{}' is claimed: run `guild release {}`".format(quest_row["slug"], tid, area), 1)


def _move(ctx, quest_row, tids_csv, target):
    tids = _split_tids(tids_csv)
    target_row = ctx.conn.execute(
        "SELECT slug, project, party, epic, state FROM quests WHERE slug = ?", (target,)
    ).fetchone()
    _require_move_target(quest_row, target_row, target)
    for tid in tids:
        _require_movable(ctx, quest_row, target, tid)
    with db.writing(ctx.conn):
        for tid in tids:
            events.record(
                ctx.conn,
                ctx.now,
                ctx.origin,
                quest_row["party"],
                ctx.session_id,
                quest_row["project"],
                "task.moved",
                "local",
                {"from_quest": quest_row["slug"], "to_quest": target, "tid": tid, "to_party": target_row["party"]},
            )
    return "\n".join(
        "task '{}/{}' moved to '{}' (party {})".format(quest_row["slug"], tid, target, target_row["party"])
        for tid in tids
    )


def move(ctx, quest, tids_csv, target):
    quest_row = _load_quest(ctx, quest)
    binding = identity.require_binding(ctx.conn, ctx.session_id)
    _require_owner(binding, quest_row)
    return _move(ctx, quest_row, tids_csv, target)


def move_for_owner(ctx, quest, tids_csv, target):
    return _move(ctx, _load_quest(ctx, quest), tids_csv, target)
