from guild import cards, config, db, events, identity, pii, polling, refs, session_info
from guild.errors import GuildError
from guild.ids import next_id


def _validate_refs(ctx, project, project_config, ref_list):
    normalized = []
    for raw in ref_list:
        parsed = refs.parse_ask_ref(raw)
        normalized.append(parsed)
        if parsed.startswith("pr:"):
            repo_and_number = parsed[len("pr:") :]
            repo, number = repo_and_number.rsplit("#", 1)
            row = ctx.conn.execute("SELECT repo FROM prs WHERE repo = ? AND number = ?", (repo, int(number))).fetchone()
            if row is None:
                raise GuildError("ask ref '{}' does not match a tracked PR".format(raw), 1)
        elif parsed.startswith("card:"):
            if not cards.card_known(ctx, project, project_config, parsed[len("card:") :]):
                raise GuildError("ask ref '{}' does not match a known card".format(raw), 1)
        else:
            quest, tid = parsed[len("task:") :].split("/", 1)
            row = ctx.conn.execute("SELECT tid FROM quest_tasks WHERE quest = ? AND tid = ?", (quest, tid)).fetchone()
            held = ctx.conn.execute("SELECT id FROM adventurers WHERE task = ?", (parsed[len("task:") :],)).fetchone()
            if row is None and held is None:
                raise GuildError("ask ref '{}' does not match a known task".format(raw), 1)
    return normalized


def _in_progress_tasks(conn, party):
    rows = conn.execute(
        "SELECT quest_tasks.quest AS quest, quest_tasks.tid AS tid, quest_tasks.title AS title,"
        " quests.epic AS epic FROM quest_tasks JOIN quests ON quests.slug = quest_tasks.quest"
        " WHERE quests.party = ? AND quests.state = 'active' AND quest_tasks.state = 'active'"
        " ORDER BY quest_tasks.quest, quest_tasks.tid",
        (party,),
    ).fetchall()
    return [dict(row) for row in rows]


def _task_card_key(conn, project, task):
    if project is None or task["epic"] is None:
        return None
    row = conn.execute(
        "SELECT jira_key FROM tasks WHERE project = ? AND epic = ? AND tid = ?",
        (project, task["epic"], task["tid"]),
    ).fetchone()
    if row is None:
        return None
    return row["jira_key"]


def _pr_card_keys(conn, party):
    rows = conn.execute("SELECT DISTINCT card FROM prs WHERE party = ? AND card IS NOT NULL", (party,)).fetchall()
    return [row["card"] for row in rows]


def _latest_handoff_path(conn, party):
    row = conn.execute(
        "SELECT handoff_path FROM leaders WHERE party = ? AND handoff_path IS NOT NULL"
        " ORDER BY generation DESC LIMIT 1",
        (party,),
    ).fetchone()
    if row is None:
        return None
    return row["handoff_path"]


def _origin_snapshot(ctx, party, project, in_progress):
    task_cards = [_task_card_key(ctx.conn, project, task) for task in in_progress]
    card_keys = set(_pr_card_keys(ctx.conn, party)) | {key for key in task_cards if key is not None}
    return {
        "session_id": ctx.session_id,
        "session_name": session_info.read_session_name(ctx.sessions_dir, ctx.session_id),
        "in_progress": [{"quest": task["quest"], "tid": task["tid"], "title": task["title"]} for task in in_progress],
        "epics": sorted({task["epic"] for task in in_progress if task["epic"] is not None}),
        "cards": sorted(card_keys),
        "handoff_path": _latest_handoff_path(ctx.conn, party),
    }


def _resolve_auto_ref(ref_list, in_progress):
    has_task_or_card = any(ref.startswith(("task:", "card:")) for ref in ref_list)
    if has_task_or_card or len(in_progress) != 1:
        return ref_list, None
    auto_ref = "task:{}/{}".format(in_progress[0]["quest"], in_progress[0]["tid"])
    return ref_list + [auto_ref], auto_ref


def create(ctx, question, context_text, ref_list, option_list):
    actor_party = identity.require_actor(ctx.conn, ctx.session_id)
    in_progress = _in_progress_tasks(ctx.conn, actor_party)
    ref_list, auto_ref = _resolve_auto_ref(ref_list, in_progress)
    if not ref_list:
        raise GuildError("ask needs at least one --ref (no single in-progress task to reference automatically)", 1)
    project = config.resolve_project(ctx.cwd, config.load_all_projects(ctx.projects_dir))
    patterns = pii.project_patterns(ctx.projects_dir, project)
    pii.validate_field(question, "ask question", pii.ASK_QUESTION_MAX_LENGTH, patterns)
    pii.validate_field(context_text, "ask context", pii.ASK_CONTEXT_MAX_LENGTH, patterns)
    project_config = None if project is None else config.load_project(ctx.projects_dir, project)
    normalized_refs = _validate_refs(ctx, project, project_config, ref_list)
    ask_id = next_id(ctx.conn, "asks")
    with db.writing(ctx.conn):
        events.record(
            ctx.conn,
            ctx.now,
            ctx.origin,
            actor_party,
            ctx.session_id,
            project,
            "ask.created",
            "local",
            {
                "id": ask_id,
                "party": actor_party,
                "question": question,
                "context": context_text,
                "refs": normalized_refs,
                "options": option_list,
                "snapshot": _origin_snapshot(ctx, actor_party, project, in_progress),
            },
        )
    lines = ["ask #{} created".format(ask_id)]
    if auto_ref is not None:
        lines.append("auto-ref: {}".format(auto_ref))
    lines.extend([pii.BROADCAST_REMINDER, pii.LOCAL_ONLY_REMINDER])
    return "\n".join(lines)


def answer(ctx, ask_id, text):
    if ctx.session_id is not None:
        raise GuildError(
            "ask answer runs from the human terminal or the web board, not inside a Claude Code session", 1
        )
    with db.writing(ctx.conn):
        row = ctx.conn.execute(
            "SELECT asks.id AS id, asks.state AS state, parties.project AS project FROM asks"
            " LEFT JOIN parties ON parties.name = asks.party WHERE asks.id = ?",
            (ask_id,),
        ).fetchone()
        if row is None:
            raise GuildError("unknown ask #{}".format(ask_id), 1)
        if row["state"] != "open":
            raise GuildError("ask #{} is not open".format(ask_id), 1)
        actor_party, unbound = identity.resolve_actor(ctx.conn, ctx.session_id)
        project = row["project"]
        patterns = pii.project_patterns(ctx.projects_dir, project)
        pii.validate_field(text, "answer", pii.ANSWER_MAX_LENGTH, patterns)
        events.record(
            ctx.conn,
            ctx.now,
            ctx.origin,
            actor_party,
            ctx.session_id,
            project,
            "ask.answered",
            "local",
            {"id": ask_id, "answer": text, "unbound": unbound},
        )
    return "ask #{} answered".format(ask_id)


def dismiss(ctx, ask_id):
    if ctx.session_id is not None:
        raise GuildError(
            "ask dismiss runs from the human terminal or the web board, not inside a Claude Code session", 1
        )
    with db.writing(ctx.conn):
        row = ctx.conn.execute("SELECT id, state FROM asks WHERE id = ?", (ask_id,)).fetchone()
        if row is None:
            raise GuildError("unknown ask #{}".format(ask_id), 1)
        if row["state"] != "open":
            raise GuildError("ask #{} is not open".format(ask_id), 1)
        actor_party, _ = identity.resolve_actor(ctx.conn, ctx.session_id)
        project = config.resolve_project(ctx.cwd, config.load_all_projects(ctx.projects_dir))
        events.record(
            ctx.conn,
            ctx.now,
            ctx.origin,
            actor_party,
            ctx.session_id,
            project,
            "ask.dismissed",
            "local",
            {"id": ask_id},
        )
    return "ask #{} dismissed".format(ask_id)


def _ask_state(conn, ask_id):
    row = conn.execute("SELECT state FROM asks WHERE id = ?", (ask_id,)).fetchone()
    if row is None:
        raise GuildError("unknown ask #{}".format(ask_id), 1)
    return row["state"]


def _settled_line(ask_id, state):
    if state == "answered":
        return "ask #{} answered: read it with guild asks {}".format(ask_id, ask_id), 0
    if state == "dismissed":
        return "ask #{} dismissed".format(ask_id), 0
    return None


def wait(conn, ask_id, timeout, sleep, clock):
    result = polling.until(
        lambda: _ask_state(conn, ask_id),
        lambda state: _settled_line(ask_id, state),
        timeout,
        sleep,
        clock,
    )
    if result is None:
        return "ask #{} still open after {}".format(ask_id, polling.timeout_label(timeout)), 3
    return result
