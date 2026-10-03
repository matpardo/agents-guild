import json

from guild import config, db, events, identity, merge_queue, refs, resolve, sanitize, timeutil
from guild.commands import main_status as main_status_commands
from guild.commands import raid as raid_commands
from guild.errors import GuildError

_CLOSED_LIFECYCLES = ("merged", "closed")
NEVER_MERGES_REMINDER = "guild never merges: merge in this order by hand; re-run after each merge"


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
        "checks_pending": row["checks_pending"] or 0,
        "needs_ask_answer": bool(row["needs_ask_answer"]),
        "needs_human_pr_review": bool(row["needs_human_pr_review"]),
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


def scoped_queue(records, pins, main_rows, party_names):
    scoped = [record for record in records if record["party"] in party_names]
    synced = [record["synced_at"] for record in scoped if record["synced_at"] is not None]
    scoped_repos = {record["repo"] for record in scoped}
    scoped_main = [row for row in main_rows if row["repo"] in scoped_repos]
    result = merge_queue.compute(scoped, pins, scoped_main)
    return {
        "main": result["main"],
        "queue": result["queue"],
        "synced_at": max(synced) if synced else None,
        "has_prs": bool(scoped),
    }


def load_scoped_queue(conn, party_names):
    return scoped_queue(
        open_pr_records(conn), load_pins(conn), main_status_commands.red_rows(conn), party_names
    )


def _resolve_scope(ctx, raid, party):
    if raid is not None:
        members = raid_commands.require_active_raid(ctx.conn, ctx.now, raid)
        return "raid", raid, {row["party"] for row in members}
    if party is not None:
        return "party", party, {_require_party(ctx.conn, party)}
    binding = identity.resolve_binding(ctx.conn, ctx.session_id)
    if binding is None:
        raise GuildError("no bound party: pass --raid <name> or --party <name>", 1)
    raids = raid_commands.member_raids(ctx.conn, ctx.now, binding["party"])
    if len(raids) > 1:
        raise GuildError(
            "party '{}' is in several raids: {}; pass --raid <name> or --party <name>".format(
                binding["party"], ", ".join(sorted(row["raid"] for row in raids))
            ),
            1,
        )
    if raids:
        return _resolve_scope(ctx, raids[0]["raid"], None)
    return "party", binding["party"], {binding["party"]}


def _require_party(conn, party):
    row = conn.execute("SELECT name FROM parties WHERE name = ?", (party,)).fetchone()
    if row is None:
        raise GuildError("unknown party '{}'".format(party), 1)
    return row["name"]


def _synced_label(now, synced_at):
    if synced_at is None:
        return "never synced"
    minutes = int((now - timeutil.from_iso(synced_at)).total_seconds() // 60)
    return "synced {} min ago".format(max(minutes, 0))


def main_label(row):
    return "{} \u2014 {} ({})".format(row["repo"], row["reason"], row["source"])


def _main_line(row):
    return "0. MAIN RED {} \u2192 fix before anything".format(main_label(row))


def _action_text(entry):
    if entry["state"] == "blocked" or not entry["why"]:
        return entry["action"]
    return "{} ({})".format(entry["action"], entry["why"])


def _task_text(entry):
    task = entry["task"] or "-"
    if not entry["labels"]:
        return task
    return "{} {}".format(task, " ".join("[{}]".format(label) for label in entry["labels"]))


def _queue_line(position, entry):
    prefix = "\u25b6 next action: " if entry["next_action"] else ""
    return "{}{}. {}  {}  {}  unblocks {} \u2014 {}".format(
        prefix, position, entry["ref"], entry["party"], _task_text(entry), entry["unblocks"], _action_text(entry)
    )


def _body_lines(scoped):
    if not scoped["has_prs"]:
        return ["no open tracked PRs"]
    lines = [_main_line(row) for row in scoped["main"]]
    lines.extend(_queue_line(index, entry) for index, entry in enumerate(scoped["queue"], start=1))
    return lines


def run(ctx, raid, party):
    kind, name, party_names = _resolve_scope(ctx, raid, party)
    scoped = load_scoped_queue(ctx.conn, party_names)
    header = "merge queue \u00b7 {} {} \u00b7 {}".format(kind, name, _synced_label(ctx.now, scoped["synced_at"]))
    lines = [header] + _body_lines(scoped) + [NEVER_MERGES_REMINDER]
    return [sanitize.strip_control_sequences(line) for line in lines]


def next_to_merge(conn, party_names):
    scoped = load_scoped_queue(conn, party_names)
    for entry in scoped["queue"]:
        if entry["action"] == "merge":
            return entry["ref"]
    return None


def main_red_labels(conn, party_names):
    return [main_label(row) for row in load_scoped_queue(conn, party_names)["main"]]


def _entry_model(entry):
    return {
        "ref": entry["ref"],
        "repo": entry["repo"],
        "number": entry["number"],
        "party": entry["party"],
        "task": entry["task"],
        "lifecycle": entry["lifecycle"],
        "checks_failing": entry["checks_failing"],
        "checks_passing": entry["checks_passing"],
        "checks_pending": entry["checks_pending"],
        "labels": entry["labels"],
        "url": "https://github.com/{}/pull/{}".format(entry["repo"], entry["number"]),
    }


def _queue_entry_model(position, entry):
    return dict(
        _entry_model(entry),
        position=position,
        unblocks=entry["unblocks"],
        state=entry["state"],
        next_action=entry["next_action"],
        action=sanitize.strip_control_sequences(entry["action"]),
        why=sanitize.strip_control_sequences(entry["why"]),
        reasons=[sanitize.strip_control_sequences(reason) for reason in entry["reasons"]],
    )


def _main_model(row):
    return {
        "repo": row["repo"],
        "source": row["source"],
        "reason": sanitize.strip_control_sequences(row["reason"]),
    }


def _scope_model(now, scope, scoped):
    return {
        "scope": scope,
        "synced_at": scoped["synced_at"],
        "synced_label": _synced_label(now, scoped["synced_at"]),
        "main": [_main_model(row) for row in scoped["main"]],
        "queue": [
            _queue_entry_model(position, entry)
            for position, entry in enumerate(scoped["queue"], start=1)
        ],
    }


def board_models(conn, now, party_names):
    records = open_pr_records(conn)
    pins = load_pins(conn)
    main_rows = main_status_commands.red_rows(conn)
    grouped = raid_commands.active_raids_grouped(conn, now)
    models = []
    in_raid = set()
    for raid_name in sorted(grouped):
        members = {row["party"] for row in grouped[raid_name]}
        in_raid |= members
        models.append(_scope_model(now, "raid:{}".format(raid_name), scoped_queue(records, pins, main_rows, members)))
    for party in sorted(party_names):
        if party in in_raid:
            continue
        scoped = scoped_queue(records, pins, main_rows, {party})
        if scoped["has_prs"]:
            models.append(_scope_model(now, "party:{}".format(party), scoped))
    return models
