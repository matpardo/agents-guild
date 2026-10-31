import json

from guild import config, db, events, identity, names, pii, task_holders, timeutil
from guild.commands import achievement, drift, sync
from guild.errors import GuildError


def _resolve_epic_tasks(conn, project, epic, tasks_csv):
    epic_row = conn.execute("SELECT epic FROM epics WHERE project = ? AND epic = ?", (project, epic)).fetchone()
    if epic_row is None:
        raise GuildError("epic '{}' was never synced: run `guild sync --source sdd`".format(epic), 1)
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
            raise GuildError("task '{}' not found in epic '{}': run `guild sync --source sdd`".format(tid, epic), 1)
        tasks.append({"tid": task_row["tid"], "title": task_row["title"]})
    return tasks


def refresh_sdd_snapshot(ctx, project):
    if config.load_project(ctx.projects_dir, project).get("sdd") is None:
        return []
    try:
        failures = sync.sync_sdd(ctx, project)
    except GuildError as error:
        failures = [error.message]
    if not failures:
        return []
    return ["sdd snapshot may be stale ({}): run `guild sync --source sdd`".format("; ".join(failures))]


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


def _require_finishable_quest(ctx, slug, binding, force):
    row = ctx.conn.execute("SELECT party, project, epic, state FROM quests WHERE slug = ?", (slug,)).fetchone()
    if row is None:
        raise GuildError("unknown quest '{}'".format(slug), 1)
    if row["party"] != binding["party"]:
        raise GuildError("quest '{}' is not owned by party '{}'".format(slug, binding["party"]), 1)
    if row["state"] != "active":
        raise GuildError("quest '{}' is already {}".format(slug, row["state"]), 1)
    _gate_unfinished_tasks(ctx.conn, slug, force)
    return row


def done(ctx, slug, accept_drift, force):
    binding = identity.require_binding(ctx.conn, ctx.session_id)
    row = _require_finishable_quest(ctx, slug, binding, force)
    stale_notes = [] if row["epic"] is None else refresh_sdd_snapshot(ctx, row["project"])
    with db.writing(ctx.conn):
        row = _require_finishable_quest(ctx, slug, binding, force)
        findings = _gate_drift(ctx, row["project"], row["epic"], binding["party"], accept_drift, stale_notes)
        snapshot = achievement.build(ctx.conn, slug, ctx.now, findings)
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
        raise GuildError("quest '{}' is not owned by party '{}'".format(slug, binding["party"]), 1)
    if row["state"] != "done":
        raise GuildError("quest '{}' is not done: only done quests can be marked incomplete".format(slug), 1)
    if not reason.strip():
        raise GuildError("--reason must not be blank", 1)
    with db.writing(ctx.conn):
        if _already_marked_incomplete(ctx.conn, slug):
            raise GuildError("quest '{}' is already marked incomplete".format(slug), 1)
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
    return [{"tid": tid, "title": task_title} for tid, task_title in zip(tids, titles, strict=True)]


def _require_followup_source(ctx, binding, source):
    row = ctx.conn.execute("SELECT slug, party FROM quests WHERE slug = ?", (source,)).fetchone()
    if row is None:
        raise GuildError("unknown quest '{}'".format(source), 1)
    if row["party"] != binding["party"]:
        raise GuildError("quest '{}' is not owned by party '{}'".format(source, binding["party"]), 1)


def _require_new_slug(ctx, slug):
    existing = ctx.conn.execute("SELECT slug FROM quests WHERE slug = ?", (slug,)).fetchone()
    if existing is not None:
        raise GuildError("quest '{}' already exists".format(slug), 1)


def _record_added(ctx, party, project, slug, title, epic, tasks, followups_of, reason):
    payload = {
        "slug": slug,
        "project": project,
        "party": party,
        "epic": epic,
        "title": title,
        "tasks": tasks,
        "followups_of": followups_of,
    }
    if reason is not None:
        pii.validate_reason(reason, ctx.projects_dir, project)
        payload["reason"] = reason
    with db.writing(ctx.conn):
        if epic is not None:
            task_holders.reject_taken_tasks(
                ctx.conn, ctx.now, project, epic, tasks, "" if party is None else party, False
            )
        events.record(
            ctx.conn,
            ctx.now,
            ctx.origin,
            party,
            ctx.session_id,
            project,
            "quest.added",
            "local",
            payload,
        )
    return "quest '{}' added".format(slug)


def add_open(ctx, project, slug, title, epic, tids):
    names.validate_name(slug, "quest slug")
    _require_new_slug(ctx, slug)
    config.load_project(ctx.projects_dir, project)
    if not tids:
        raise GuildError("select at least one task", 1)
    tasks = _resolve_epic_tasks(ctx.conn, project, epic, ",".join(tids))
    return _record_added(ctx, None, project, slug, title, epic, tasks, None, None)


def add(ctx, slug, title, epic, tasks_csv, titles_csv, no_epic, followups_of, open_quest, reason):
    names.validate_name(slug, "quest slug")
    if open_quest and followups_of is not None:
        raise GuildError("--followups-of cannot be combined with --open", 1)
    if followups_of is not None and (no_epic or epic is not None):
        raise GuildError("--followups-of cannot be combined with --epic or --no-epic", 1)
    free = no_epic or followups_of is not None
    if no_epic and epic is not None:
        raise GuildError("--no-epic cannot be combined with --epic", 1)
    if titles_csv is not None and (not free or tasks_csv is None):
        raise GuildError("--titles requires --no-epic (or --followups-of) and --tasks", 1)
    if not free and epic is None:
        raise GuildError("epic quests require --epic, or pass --no-epic", 1)
    _require_new_slug(ctx, slug)
    binding = None if open_quest else identity.require_binding(ctx.conn, ctx.session_id)
    party = None if open_quest else binding["party"]
    project = config.require_project(ctx.cwd, ctx.projects_dir)
    if followups_of is not None:
        _require_followup_source(ctx, binding, followups_of)
    tasks = []
    if free and tasks_csv is not None:
        tasks = _free_tasks(tasks_csv, titles_csv)
    if not free:
        tasks = _resolve_epic_tasks(ctx.conn, project, epic, tasks_csv or "")
    return _record_added(ctx, party, project, slug, title, epic, tasks, followups_of, reason)


def _load_quest(conn, slug):
    row = conn.execute("SELECT slug, project, party, epic, state FROM quests WHERE slug = ?", (slug,)).fetchone()
    if row is None:
        raise GuildError("unknown quest '{}'".format(slug), 1)
    return row


def _take(ctx, slug, party, project):
    with db.writing(ctx.conn):
        row = _load_quest(ctx.conn, slug)
        if row["party"] is not None or row["state"] != "active":
            raise GuildError("quest '{}' is not open".format(slug), 1)
        if row["project"] != project:
            raise GuildError("quest '{}' belongs to project '{}'".format(slug, row["project"]), 1)
        events.record(
            ctx.conn,
            ctx.now,
            ctx.origin,
            party,
            ctx.session_id,
            project,
            "quest.taken",
            "local",
            {"slug": slug, "party": party},
        )
    return "quest '{}' taken".format(slug)


def take(ctx, slug):
    binding = identity.require_binding(ctx.conn, ctx.session_id)
    return _take(ctx, slug, binding["party"], binding["project"])


def take_for_party(ctx, slug, party):
    row = ctx.conn.execute("SELECT name, project, state FROM parties WHERE name = ?", (party,)).fetchone()
    if row is None:
        raise GuildError("unknown party '{}'".format(party), 1)
    if row["state"] != "active":
        raise GuildError("party '{}' is {}".format(party, row["state"]), 1)
    return _take(ctx, slug, row["name"], row["project"])


def release_blockers(ctx, row):
    blockers = []
    tasks = ctx.conn.execute(
        "SELECT tid, state FROM quest_tasks WHERE quest = ? ORDER BY tid", (row["slug"],)
    ).fetchall()
    blockers.extend("{} is {}".format(task["tid"], task["state"]) for task in tasks if task["state"] != "queued")
    prs = ctx.conn.execute(
        "SELECT repo, number FROM prs WHERE task_quest = ?"
        " AND COALESCE(gh_state, 'OPEN') = 'OPEN' AND lifecycle NOT IN ('merged', 'closed')",
        (row["slug"],),
    ).fetchall()
    blockers.extend("open PR {}#{}".format(pr["repo"], pr["number"]) for pr in prs)
    prefix = task_holders.TASK_CLAIM_PREFIX.format(row["epic"] or row["slug"])
    claims = ctx.conn.execute(
        "SELECT area, expires_at FROM claims WHERE project = ? AND party = ?", (row["project"], row["party"])
    ).fetchall()
    task_tids = {task["tid"] for task in tasks}
    for claim in claims:
        if not claim["area"].startswith(prefix) or timeutil.is_expired(ctx.now, claim["expires_at"]):
            continue
        if claim["area"][len(prefix) :] in task_tids:
            blockers.append("claim {}".format(claim["area"]))
    return blockers


def _release(ctx, row):
    with db.writing(ctx.conn):
        current = _load_quest(ctx.conn, row["slug"])
        if current["party"] is None:
            raise GuildError("quest '{}' is already open".format(row["slug"]), 1)
        if current["state"] != "active":
            raise GuildError("quest '{}' is already {}".format(row["slug"], current["state"]), 1)
        blockers = release_blockers(ctx, current)
        if blockers:
            raise GuildError("quest '{}' cannot be released: {}".format(row["slug"], "; ".join(blockers)), 1)
        events.record(
            ctx.conn,
            ctx.now,
            ctx.origin,
            row["party"],
            ctx.session_id,
            row["project"],
            "quest.released",
            "local",
            {"slug": row["slug"], "party": row["party"]},
        )
    return "quest '{}' released".format(row["slug"])


def release(ctx, slug):
    binding = identity.require_binding(ctx.conn, ctx.session_id)
    row = _load_quest(ctx.conn, slug)
    if row["party"] != binding["party"]:
        raise GuildError("quest '{}' is not owned by party '{}'".format(slug, binding["party"]), 1)
    return _release(ctx, row)


def release_for_owner(ctx, slug):
    return _release(ctx, _load_quest(ctx.conn, slug))
