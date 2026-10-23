import json

from guild import config, db, events, identity, names, timeutil
from guild.commands import achievement, drift, sync
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


def adventurer_holder(conn, project, epic, tid):
    row = conn.execute(
        "SELECT id FROM adventurers WHERE project = ? AND task = ? AND state = 'active'",
        (project, "{}/{}".format(epic, tid)),
    ).fetchone()
    if row is None:
        return None
    return row["id"]


def reject_taken_tasks(conn, now, project, epic, tasks, party):
    quest_holders = _quest_holders(conn, project, epic, party)
    claim_holders = _claim_holders(conn, now, project, epic, party)
    conflicts = []
    for task in tasks:
        tid = task["tid"]
        adventurer_id = adventurer_holder(conn, project, epic, tid)
        if adventurer_id is not None:
            conflicts.append("{} is held by adventurer {}".format(tid, adventurer_id))
            continue
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


def refresh_sdd_snapshot(ctx, project):
    if config.load_project(ctx.projects_dir, project).get("sdd") is None:
        return []
    try:
        failures = sync.sync_sdd(ctx, project)
    except GuildError as error:
        failures = [error.message]
    if not failures:
        return []
    return [
        "sdd snapshot may be stale ({}): run `guild sync --source sdd`".format("; ".join(failures))
    ]


def _owner_sections(split):
    lines = []
    if split["own"]:
        lines.append("yours:")
        lines.extend(split["own"])
    if split["foreign"]:
        lines.append("other parties:")
        lines.extend("{} (party {})".format(item["text"], item["party"]) for item in split["foreign"])
    return lines


def _gate_drift(ctx, project, epic, party, accept_drift, stale_notes):
    if epic is None:
        return []
    split = drift.epic_findings_by_owner(ctx.conn, project, epic, party)
    findings = split["own"] + [item["text"] for item in split["foreign"]]
    if findings and not accept_drift:
        raise GuildError(
            "drift in epic '{}', fix it or pass --accept-drift:\n{}".format(
                epic, "\n".join(_owner_sections(split) + stale_notes)
            ),
            1,
        )
    return findings


def _unfinished_task_lines(conn, slug):
    rows = conn.execute(
        "SELECT tid, state FROM quest_tasks WHERE quest = ? AND state != 'done' ORDER BY tid", (slug,)
    ).fetchall()
    return ["{} ({})".format(row["tid"], row["state"]) for row in rows]


def _gate_unfinished_tasks(conn, slug, force):
    lines = _unfinished_task_lines(conn, slug)
    if not lines or force:
        return
    raise GuildError(
        "quest '{}' has tasks not done, finish them or pass --force:\n{}".format(slug, "\n".join(lines)), 1
    )


def unfinished_work(conn, slug, project, epic):
    problems = []
    task_lines = _unfinished_task_lines(conn, slug)
    if task_lines:
        problems.append("quest '{}' has tasks not done:\n{}".format(slug, "\n".join(task_lines)))
    findings = [] if epic is None else drift.epic_findings(conn, project, epic)
    if findings:
        problems.append("quest '{}' has drift in epic '{}':\n{}".format(slug, epic, "\n".join(findings)))
    return problems


def done(ctx, slug, accept_drift, force):
    binding = identity.require_binding(ctx.conn, ctx.session_id)
    row = ctx.conn.execute(
        "SELECT party, project, epic, state FROM quests WHERE slug = ?", (slug,)
    ).fetchone()
    if row is None:
        raise GuildError("unknown quest '{}'".format(slug), 1)
    if row["party"] != binding["party"]:
        raise GuildError(
            "quest '{}' is not owned by party '{}'".format(slug, binding["party"]), 1
        )
    if row["state"] != "active":
        raise GuildError("quest '{}' is already {}".format(slug, row["state"]), 1)
    _gate_unfinished_tasks(ctx.conn, slug, force)
    stale_notes = [] if row["epic"] is None else refresh_sdd_snapshot(ctx, row["project"])
    findings = _gate_drift(
        ctx, row["project"], row["epic"], binding["party"], accept_drift, stale_notes
    )
    snapshot = achievement.build(ctx.conn, slug, ctx.now, findings)
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
            {"slug": slug, "achievement": snapshot},
        )
    return "quest '{}' done".format(slug)


def _already_marked_incomplete(conn, slug):
    rows = conn.execute("SELECT payload FROM events WHERE kind = 'quest.marked_incomplete'").fetchall()
    return any(json.loads(row["payload"])["slug"] == slug for row in rows)


def incomplete(ctx, slug, reason):
    binding = identity.require_binding(ctx.conn, ctx.session_id)
    row = ctx.conn.execute("SELECT party, project, state FROM quests WHERE slug = ?", (slug,)).fetchone()
    if row is None:
        raise GuildError("unknown quest '{}'".format(slug), 1)
    if row["party"] != binding["party"]:
        raise GuildError(
            "quest '{}' is not owned by party '{}'".format(slug, binding["party"]), 1
        )
    if row["state"] != "done":
        raise GuildError("quest '{}' is not done: only done quests can be marked incomplete".format(slug), 1)
    if not reason.strip():
        raise GuildError("--reason must not be blank", 1)
    if _already_marked_incomplete(ctx.conn, slug):
        raise GuildError("quest '{}' is already marked incomplete".format(slug), 1)
    with db.writing(ctx.conn):
        events.record(
            ctx.conn,
            ctx.now,
            ctx.origin,
            binding["party"],
            ctx.session_id,
            row["project"],
            "quest.marked_incomplete",
            "local",
            {"slug": slug, "reason": reason.strip()},
        )
    return "quest '{}' marked incomplete".format(slug)


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


def _require_followup_source(ctx, binding, source):
    row = ctx.conn.execute("SELECT slug, party FROM quests WHERE slug = ?", (source,)).fetchone()
    if row is None:
        raise GuildError("unknown quest '{}'".format(source), 1)
    if row["party"] != binding["party"]:
        raise GuildError(
            "quest '{}' is not owned by party '{}'".format(source, binding["party"]), 1
        )


def add(ctx, slug, title, epic, tasks_csv, titles_csv, no_epic, followups_of):
    names.validate_name(slug, "quest slug")
    if followups_of is not None and (no_epic or epic is not None):
        raise GuildError("--followups-of cannot be combined with --epic or --no-epic", 1)
    free = no_epic or followups_of is not None
    if no_epic and epic is not None:
        raise GuildError("--no-epic cannot be combined with --epic", 1)
    if titles_csv is not None and (not free or tasks_csv is None):
        raise GuildError("--titles requires --no-epic (or --followups-of) and --tasks", 1)
    if not free and epic is None:
        raise GuildError("epic quests require --epic, or pass --no-epic", 1)
    existing = ctx.conn.execute("SELECT slug FROM quests WHERE slug = ?", (slug,)).fetchone()
    if existing is not None:
        raise GuildError("quest '{}' already exists".format(slug), 1)
    binding = identity.require_binding(ctx.conn, ctx.session_id)
    project = config.require_project(ctx.cwd, ctx.projects_dir)
    if followups_of is not None:
        _require_followup_source(ctx, binding, followups_of)
    tasks = []
    if free and tasks_csv is not None:
        tasks = _free_tasks(tasks_csv, titles_csv)
    if not free:
        tasks = _resolve_epic_tasks(ctx.conn, project, epic, tasks_csv or "")
        reject_taken_tasks(ctx.conn, ctx.now, project, epic, tasks, binding["party"])
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
                "followups_of": followups_of,
            },
        )
    return "quest '{}' added".format(slug)
