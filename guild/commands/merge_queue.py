import json

from guild import config, db, events, identity, merge_queue, refs, resolve
from guild.commands import raid as raid_commands
from guild.errors import GuildError

_CLOSED_LIFECYCLES = ("merged", "closed")


def _ref_text(repo, number):
    return "{}#{}".format(repo, number)


def _task_context(conn, row):
    if row["task_quest"] is None:
        return None
    quest = conn.execute(
        "SELECT project, epic FROM quests WHERE slug = ?", (row["task_quest"],)
    ).fetchone()
    if quest is None or quest["epic"] is None:
        return None
    return quest["project"], quest["epic"]


def _task_deps(conn, project, epic, tid):
    task = conn.execute(
        "SELECT deps FROM tasks WHERE project = ? AND epic = ? AND tid = ?", (project, epic, tid)
    ).fetchone()
    if task is None:
        return []
    return json.loads(task["deps"])


def _unmet_deps(conn, project, epic, deps):
    return [dep for dep in deps if not resolve.resolve_task_done(conn, project, epic, dep)[0]]


def _globs(conn, row):
    rows = conn.execute(
        "SELECT glob FROM pr_shared_areas WHERE repo = ? AND number = ? ORDER BY glob",
        (row["repo"], row["number"]),
    ).fetchall()
    return [glob_row["glob"] for glob_row in rows]


def _pr_record(conn, row):
    context = _task_context(conn, row)
    task_key = None
    dep_keys = []
    unmet = []
    if context is not None:
        project, epic = context
        deps = _task_deps(conn, project, epic, row["task_tid"])
        task_key = (project, epic, row["task_tid"])
        dep_keys = [(project, epic, dep) for dep in deps]
        unmet = _unmet_deps(conn, project, epic, deps)
    return {
        "ref": _ref_text(row["repo"], row["number"]),
        "repo": row["repo"],
        "number": row["number"],
        "party": row["party"],
        "quest": row["task_quest"],
        "tid": row["task_tid"],
        "lifecycle": row["lifecycle"],
        "checks_failing": row["checks_failing"] or 0,
        "checks_passing": row["checks_passing"] or 0,
        "mergeable": row["mergeable"],
        "additions": row["additions"] or 0,
        "deletions": row["deletions"] or 0,
        "created_at": row["created_at"],
        "globs": _globs(conn, row),
        "task_key": task_key,
        "dep_keys": dep_keys,
        "unmet_deps": unmet,
        "synced_at": row["synced_at"],
    }


def open_pr_records(conn):
    rows = conn.execute(
        "SELECT * FROM prs WHERE lifecycle NOT IN ('merged', 'closed') ORDER BY repo ASC, number ASC"
    ).fetchall()
    return [_pr_record(conn, row) for row in rows]


def load_pins(conn):
    rows = conn.execute(
        "SELECT * FROM merge_queue_pins ORDER BY first_repo, first_number, second_repo, second_number"
    ).fetchall()
    return [
        {
            "first": _ref_text(row["first_repo"], row["first_number"]),
            "second": _ref_text(row["second_repo"], row["second_number"]),
            "author": row["party"],
        }
        for row in rows
    ]


def _tracked_row(conn, repo, number):
    row = conn.execute("SELECT * FROM prs WHERE repo = ? AND number = ?", (repo, number)).fetchone()
    if row is None:
        raise GuildError("PR '{}' is not tracked".format(_ref_text(repo, number)), 1)
    return row


def _require_open(row):
    if row["lifecycle"] in _CLOSED_LIFECYCLES:
        raise GuildError(
            "PR '{}' is {}: only open PRs can be pinned".format(
                _ref_text(row["repo"], row["number"]), row["lifecycle"]
            ),
            1,
        )


def _actor_party(ctx):
    if ctx.session_id is None:
        return None
    return identity.require_binding(ctx.conn, ctx.session_id)["party"]


def _shared_raid_names(ctx, first, second):
    first_raids = raid_commands.member_raid_names(ctx.conn, ctx.now, first["party"])
    second_raids = raid_commands.member_raid_names(ctx.conn, ctx.now, second["party"])
    return sorted(first_raids & second_raids)


def _lead_party(ctx, raid_name):
    lead = raid_commands.active_lead(ctx.conn, ctx.now, raid_name)
    if lead is None:
        return None
    return lead["party"]


def _require_raid_authority(ctx, actor, raid_names):
    leads = {raid_name: _lead_party(ctx, raid_name) for raid_name in raid_names}
    if actor in leads.values():
        return
    described = ", ".join(
        "'{}' (lead: {})".format(raid_name, leads[raid_name] or "none") for raid_name in raid_names
    )
    raise GuildError(
        "both PRs belong to members of raid {}: only the raid lead or the human may pin".format(described),
        1,
    )


def _require_authority(ctx, actor, first, second):
    if actor is None:
        return
    raid_names = _shared_raid_names(ctx, first, second)
    if raid_names:
        _require_raid_authority(ctx, actor, raid_names)
        return
    if first["party"] == actor and second["party"] == actor:
        return
    raise GuildError(
        "party '{}' does not own both PRs: only the owning party or the human may pin".format(actor), 1
    )


def _existing_pin(conn, first, second):
    return conn.execute(
        "SELECT party FROM merge_queue_pins WHERE first_repo = ? AND first_number = ?"
        " AND second_repo = ? AND second_number = ?",
        (first["repo"], first["number"], second["repo"], second["number"]),
    ).fetchone()


def _open_pin_pairs(conn, open_refs):
    return [
        (pin["first"], pin["second"])
        for pin in load_pins(conn)
        if pin["first"] in open_refs and pin["second"] in open_refs
    ]


def _reject_cycle(conn, first_ref, second_ref):
    records = open_pr_records(conn)
    open_refs = {record["ref"] for record in records}
    pairs = merge_queue.dependency_pairs(records) + _open_pin_pairs(conn, open_refs)
    path = merge_queue.find_path(pairs, second_ref, first_ref)
    if path is None:
        return
    raise GuildError("pin would create a cycle: {} -> {}".format(first_ref, " -> ".join(path)), 1)


def _project_for_repo(ctx, repo):
    for project in config.load_all_projects(ctx.projects_dir):
        if repo in project["github"]["repos"]:
            return project["name"]
    return None


def _record_pin_event(ctx, kind, actor, first, second):
    with db.writing(ctx.conn):
        events.record(
            ctx.conn,
            ctx.now,
            ctx.origin,
            actor,
            ctx.session_id,
            _project_for_repo(ctx, first["repo"]),
            kind,
            "guild",
            {
                "first_repo": first["repo"],
                "first_number": first["number"],
                "second_repo": second["repo"],
                "second_number": second["number"],
                "author": actor,
            },
        )


def _pin_rows(ctx, first_text, second_text):
    first_repo, first_number = refs.parse_pr_ref(first_text)
    second_repo, second_number = refs.parse_pr_ref(second_text)
    if (first_repo, first_number) == (second_repo, second_number):
        raise GuildError("cannot pin '{}' before itself".format(first_text), 1)
    first = _tracked_row(ctx.conn, first_repo, first_number)
    second = _tracked_row(ctx.conn, second_repo, second_number)
    return first, second


def pin(ctx, first_text, second_text):
    first, second = _pin_rows(ctx, first_text, second_text)
    _require_open(first)
    _require_open(second)
    actor = _actor_party(ctx)
    _require_authority(ctx, actor, first, second)
    first_ref = _ref_text(first["repo"], first["number"])
    second_ref = _ref_text(second["repo"], second["number"])
    if _existing_pin(ctx.conn, first, second) is not None:
        raise GuildError("'{}' is already pinned before '{}'".format(first_ref, second_ref), 1)
    _reject_cycle(ctx.conn, first_ref, second_ref)
    _record_pin_event(ctx, "merge_queue.pinned", actor, first, second)
    return "pinned '{}' before '{}'".format(first_ref, second_ref)


def unpin(ctx, first_text, second_text):
    first, second = _pin_rows(ctx, first_text, second_text)
    first_ref = _ref_text(first["repo"], first["number"])
    second_ref = _ref_text(second["repo"], second["number"])
    if _existing_pin(ctx.conn, first, second) is None:
        raise GuildError("no pin of '{}' before '{}'".format(first_ref, second_ref), 1)
    actor = _actor_party(ctx)
    _require_authority(ctx, actor, first, second)
    _record_pin_event(ctx, "merge_queue.unpinned", actor, first, second)
    return "unpinned '{}' before '{}'".format(first_ref, second_ref)
