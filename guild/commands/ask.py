from guild import config, db, events, identity, pii, refs
from guild.ids import next_id
from guild.errors import GuildError


def _validate_refs(ctx, ref_list):
    normalized = []
    for raw in ref_list:
        parsed = refs.parse_ask_ref(raw)
        normalized.append(parsed)
        if parsed.startswith("pr:"):
            repo_and_number = parsed[len("pr:"):]
            repo, number = repo_and_number.rsplit("#", 1)
            row = ctx.conn.execute(
                "SELECT repo FROM prs WHERE repo = ? AND number = ?", (repo, int(number))
            ).fetchone()
            if row is None:
                raise GuildError("ask ref '{}' does not match a tracked PR".format(raw), 1)
        else:
            quest, tid = parsed[len("task:"):].split("/", 1)
            row = ctx.conn.execute(
                "SELECT tid FROM quest_tasks WHERE quest = ? AND tid = ?", (quest, tid)
            ).fetchone()
            if row is None:
                raise GuildError("ask ref '{}' does not match a known task".format(raw), 1)
    return normalized


def create(ctx, question, context_text, ref_list, option_list):
    if not ref_list:
        raise GuildError("ask needs at least one --ref", 1)
    binding = identity.require_binding(ctx.conn, ctx.session_id)
    project = config.resolve_project(ctx.cwd, config.load_all_projects(ctx.projects_dir))
    patterns = pii.project_patterns(ctx.projects_dir, project)
    pii.validate_field(question, "ask question", pii.ASK_QUESTION_MAX_LENGTH, patterns)
    pii.validate_field(context_text, "ask context", pii.ASK_CONTEXT_MAX_LENGTH, patterns)
    normalized_refs = _validate_refs(ctx, ref_list)
    ask_id = next_id(ctx.conn, "asks")
    with db.writing(ctx.conn):
        events.record(
            ctx.conn,
            ctx.now,
            ctx.origin,
            binding["party"],
            ctx.session_id,
            project,
            "ask.created",
            "local",
            {
                "id": ask_id,
                "party": binding["party"],
                "question": question,
                "context": context_text,
                "refs": normalized_refs,
                "options": option_list,
            },
        )
    return "ask #{} created\n{}".format(ask_id, pii.BROADCAST_REMINDER)


def answer(ctx, ask_id, text):
    row = ctx.conn.execute(
        "SELECT asks.id AS id, asks.state AS state, parties.project AS project FROM asks"
        " LEFT JOIN parties ON parties.name = asks.party WHERE asks.id = ?",
        (ask_id,),
    ).fetchone()
    if row is None:
        raise GuildError("unknown ask #{}".format(ask_id), 1)
    if row["state"] != "open":
        raise GuildError("ask #{} is not open".format(ask_id), 1)
    binding = identity.resolve_binding(ctx.conn, ctx.session_id)
    actor_party = binding["party"] if binding is not None else None
    project = row["project"]
    patterns = pii.project_patterns(ctx.projects_dir, project)
    pii.validate_field(text, "answer", pii.ANSWER_MAX_LENGTH, patterns)
    with db.writing(ctx.conn):
        events.record(
            ctx.conn,
            ctx.now,
            ctx.origin,
            actor_party,
            ctx.session_id,
            project,
            "ask.answered",
            "local",
            {"id": ask_id, "answer": text},
        )
    return "ask #{} answered".format(ask_id)


def dismiss(ctx, ask_id):
    row = ctx.conn.execute("SELECT id, state FROM asks WHERE id = ?", (ask_id,)).fetchone()
    if row is None:
        raise GuildError("unknown ask #{}".format(ask_id), 1)
    if row["state"] != "open":
        raise GuildError("ask #{} is not open".format(ask_id), 1)
    binding = identity.resolve_binding(ctx.conn, ctx.session_id)
    actor_party = binding["party"] if binding is not None else None
    project = config.resolve_project(ctx.cwd, config.load_all_projects(ctx.projects_dir))
    with db.writing(ctx.conn):
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
