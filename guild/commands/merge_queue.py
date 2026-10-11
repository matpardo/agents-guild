import json

from guild import config, db, events, identity, merge_queue, pr_asks, refs, resolve, sanitize, timeutil
from guild.commands import main_status as main_status_commands
from guild.commands import raid as raid_commands
from guild.errors import GuildError

_CLOSED_LIFECYCLES = ("merged", "closed")
_DRAFT_LIFECYCLES = ("draft", "converging")
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


def _optional_branch(branch):
    if not branch:
        return None
    return sanitize.strip_control_sequences(branch)


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
        "card": row["card"],
        "lifecycle": row["lifecycle"],
        "checks_failing": row["checks_failing"] or 0,
        "checks_passing": row["checks_passing"] or 0,
        "checks_pending": row["checks_pending"] or 0,
        "needs_ask_answer": pr_asks.needs_answer(row),
        "ask_id": row["open_ask_id"],
        "needs_human_pr_review": bool(row["needs_human_pr_review"]),
        "branch": _optional_branch(row["branch"]),
        "base_branch": _optional_branch(row["base_branch"]),
        "fixes_main": bool(row["fixes_main"]),
        "fixes_flaky": bool(row["fixes_flaky"]),
        "blocked_external": row["blocked_external"],
        "mergeable": row["mergeable"],
        "review_decision": row["review_decision"],
        "unresolved_threads": row["unresolved_threads"],
        "merge_state": row["merge_state"],
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
        pr_asks.PRS_WITH_ASK_SQL + " WHERE lifecycle NOT IN ('merged', 'closed') ORDER BY repo ASC, number ASC"
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
    pairs = merge_queue.dependency_pairs(records) + merge_queue.stack_pairs(records) + _open_pin_pairs(conn, open_refs)
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
    brackets = entry["labels"]
    if not brackets:
        return task
    return "{} {}".format(task, " ".join("[{}]".format(text) for text in brackets))


def _branch_suffix(entry):
    if entry["branch"] is None:
        return ""
    return "  branch: {}".format(entry["branch"])


def _queue_line(position, entry):
    prefix = "\u25b6 next action: " if entry["next_action"] else ""
    return "{}{}. {}  {}  {}  unblocks {} \u2014 {}{}".format(
        prefix,
        position,
        entry["ref"],
        entry["party"],
        _task_text(entry),
        entry["unblocks"],
        _action_text(entry),
        _branch_suffix(entry),
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


def _first_to_merge(scoped):
    for entry in scoped["queue"]:
        if entry["action"] == "merge":
            return entry
    return None


def head_entry(conn, party_names):
    return _first_to_merge(load_scoped_queue(conn, party_names))


def next_to_merge(conn, party_names):
    entry = head_entry(conn, party_names)
    if entry is None:
        return None
    return entry["ref"]


def head_line(ctx, raid, party):
    _, _, party_names = _resolve_scope(ctx, raid, party)
    entry = head_entry(ctx.conn, party_names)
    if entry is None:
        return "no PR ready to merge"
    return sanitize.strip_control_sequences("{} {} {}".format(entry["ref"], entry["party"], entry["task"] or "-"))


def scope_heads(conn, now):
    records = open_pr_records(conn)
    pins = load_pins(conn)
    main_rows = main_status_commands.red_rows(conn)
    grouped = raid_commands.active_raids_grouped(conn, now)
    heads = []
    in_raid = set()
    for raid_name in sorted(grouped):
        members = {row["party"] for row in grouped[raid_name]}
        in_raid |= members
        heads.append(("raid:{}".format(raid_name), _first_to_merge(scoped_queue(records, pins, main_rows, members))))
    solo = {record["party"] for record in records} - in_raid
    for party in sorted(solo):
        heads.append(("party:{}".format(party), _first_to_merge(scoped_queue(records, pins, main_rows, {party}))))
    return [(scope, entry) for scope, entry in heads if entry is not None]


def external_blocked_refs(conn):
    queue = merge_queue.compute(open_pr_records(conn), load_pins(conn), [])["queue"]
    return {entry["ref"] for entry in queue if entry["external"] is not None}


def file_pr_rows(conn, external, repo, path, exclude_branch):
    found = conn.execute(
        "SELECT prs.repo, prs.number, prs.party FROM pr_files JOIN prs"
        " ON prs.repo = pr_files.repo AND prs.number = pr_files.number"
        " WHERE prs.repo = ? AND pr_files.path = ? AND prs.lifecycle NOT IN ('merged', 'closed')"
        " AND (? IS NULL OR prs.branch IS NULL OR prs.branch != ?) ORDER BY prs.number",
        (repo, path, exclude_branch, exclude_branch),
    ).fetchall()
    return [row for row in found if _ref_text(row["repo"], row["number"]) not in external]


def hot_files(conn, repos, cap):
    marks = ",".join("?" * len(repos))
    paths = conn.execute(
        "SELECT DISTINCT pr_files.repo, pr_files.path FROM pr_files JOIN prs"
        " ON prs.repo = pr_files.repo AND prs.number = pr_files.number"
        " WHERE prs.repo IN ({}) AND prs.lifecycle NOT IN ('merged', 'closed')"
        " ORDER BY pr_files.repo, pr_files.path".format(marks),
        sorted(repos),
    ).fetchall()
    external = external_blocked_refs(conn)
    hot = []
    for row in paths:
        rows = file_pr_rows(conn, external, row["repo"], row["path"], None)
        if len(rows) >= cap:
            hot.append(
                {"repo": row["repo"], "path": row["path"], "prs": [_ref_text(r["repo"], r["number"]) for r in rows]}
            )
    return hot


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
        "branch": entry["branch"],
        "checks_failing": entry["checks_failing"],
        "checks_passing": entry["checks_passing"],
        "checks_pending": entry["checks_pending"],
        "labels": entry["labels"],
        "url": "https://github.com/{}/pull/{}".format(entry["repo"], entry["number"]),
    }


def gates(entry, red_rows):
    found = []
    if entry["lifecycle"] in _DRAFT_LIFECYCLES:
        found.append("draft (gh pr ready {})".format(entry["number"]))
    if "needs-human-pr-review" in entry["labels"]:
        found.append("needs human review")
    found.extend(
        "main red {}".format(main_label(row)) for row in red_rows if row["repo"] == entry["repo"]
    )
    return found


def _queue_entry_model(position, entry, main_rows):
    return dict(
        _entry_model(entry),
        position=position,
        unblocks=entry["unblocks"],
        state=entry["state"],
        next_action=entry["next_action"],
        action=sanitize.strip_control_sequences(entry["action"]),
        why=sanitize.strip_control_sequences(entry["why"]),
        reasons=[sanitize.strip_control_sequences(reason) for reason in entry["reasons"]],
        blockers=[sanitize.strip_control_sequences(blocker) for blocker in entry["blockers"]],
        waits=[sanitize.strip_control_sequences(wait) for wait in entry["waits"]],
        gates=[sanitize.strip_control_sequences(gate) for gate in gates(entry, main_rows)],
    )


def _main_model(row):
    return {
        "repo": row["repo"],
        "source": row["source"],
        "reason": sanitize.strip_control_sequences(row["reason"]),
    }


def _head_model(scoped):
    entry = _first_to_merge(scoped)
    if entry is None:
        return None
    return {"ref": entry["ref"], "party": entry["party"], "url": "https://github.com/{}/pull/{}".format(entry["repo"], entry["number"])}


def _scope_model(now, scope, scoped):
    return {
        "head": _head_model(scoped),
        "scope": scope,
        "synced_at": scoped["synced_at"],
        "synced_label": _synced_label(now, scoped["synced_at"]),
        "main": [_main_model(row) for row in scoped["main"]],
        "queue": [
            _queue_entry_model(position, entry, scoped["main"])
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
