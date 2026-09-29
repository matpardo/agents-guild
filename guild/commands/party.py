from pathlib import Path

from guild import config, db, events, identity, names, session_info
from guild.commands import claim as claim_commands
from guild.commands import next as next_commands
from guild.errors import GuildError


def previous_handoff_content(conn, party, generation):
    row = conn.execute(
        "SELECT handoff_path FROM leaders WHERE party = ? AND generation = ?",
        (party, generation - 1),
    ).fetchone()
    if row is None or row["handoff_path"] is None:
        return None
    path = Path(row["handoff_path"])
    if not path.is_file():
        return None
    return path.read_text().rstrip()


def start(ctx, name):
    names.validate_name(name, "party name")
    if ctx.session_id is None:
        raise GuildError("party start requires a Claude Code session", 1)
    existing = ctx.conn.execute("SELECT name FROM parties WHERE name = ?", (name,)).fetchone()
    if existing is not None:
        raise GuildError(
            "party '{}' already exists: use `guild party resume {}`".format(name, name), 1
        )
    projects = config.load_all_projects(ctx.projects_dir)
    project = config.resolve_project(ctx.cwd, projects)
    session_name = session_info.read_session_name(ctx.sessions_dir, ctx.session_id)
    with db.writing(ctx.conn):
        events.record(
            ctx.conn,
            ctx.now,
            ctx.origin,
            name,
            ctx.session_id,
            project,
            "party.started",
            "local",
            {"party": name, "session_name": session_name},
        )
    return "party '{}' started, generation 1".format(name)


def _resolve_resume_session_id(ctx, session_name):
    if session_name is not None:
        if ctx.session_id is not None:
            raise GuildError("--session cannot be used from inside a Claude Code session", 1)
        session_id = session_info.resolve_session_id(ctx.sessions_dir, session_name)
        if session_id is None:
            raise GuildError("no session named '{}' found in {}".format(session_name, ctx.sessions_dir), 1)
        return session_id
    if ctx.session_id is None:
        raise GuildError("party resume requires a Claude Code session", 1)
    return ctx.session_id


def resume(ctx, name, session_name):
    names.validate_name(name, "party name")
    session_id = _resolve_resume_session_id(ctx, session_name)
    row = ctx.conn.execute(
        "SELECT project, generation, state FROM parties WHERE name = ?", (name,)
    ).fetchone()
    if row is None:
        raise GuildError("unknown party '{}'".format(name), 1)
    if row["state"] == "closed":
        raise GuildError("party '{}' is closed".format(name), 1)
    generation = row["generation"] + 1
    resolved_session_name = session_name or session_info.read_session_name(ctx.sessions_dir, session_id)
    with db.writing(ctx.conn):
        events.record(
            ctx.conn,
            ctx.now,
            ctx.origin,
            name,
            session_id,
            row["project"],
            "party.resumed",
            "local",
            {"party": name, "generation": generation, "session_name": resolved_session_name},
        )
    lines = ["party '{}' resumed, generation {}".format(name, generation)]
    handoff_content = previous_handoff_content(ctx.conn, name, generation)
    if handoff_content is not None:
        lines += ["", handoff_content, ""]
        binding = identity.resolve_binding(ctx.conn, session_id)
        lines.extend(next_commands.run(ctx, binding, False, False))
    return "\n".join(lines)


def _close_target(ctx, name):
    if name is None:
        return identity.require_binding(ctx.conn, ctx.session_id)["party"]
    names.validate_name(name, "party name")
    if ctx.session_id is None:
        return name
    binding = identity.resolve_binding(ctx.conn, ctx.session_id)
    if binding is None or binding["party"] != name:
        raise GuildError(
            "cannot close another party from a session: run `guild party close {}` from a terminal".format(name), 1
        )
    return name


def _count(amount, noun):
    return "{} {}{}".format(amount, noun, "" if amount == 1 else "s")


def _cleanup_summary(ctx, party):
    quests = ctx.conn.execute(
        "SELECT COUNT(*) AS n FROM quests WHERE party = ? AND state = 'active'", (party,)
    ).fetchone()["n"]
    asks = ctx.conn.execute(
        "SELECT COUNT(*) AS n FROM asks WHERE party = ? AND state = 'open'", (party,)
    ).fetchone()["n"]
    claims = len([row for row in claim_commands.list_claims(ctx.conn, ctx.now) if row["party"] == party])
    return "{} done, {} dismissed, {} released".format(
        _count(quests, "quest"), _count(asks, "ask"), _count(claims, "claim")
    )


def _open_pr_refs(conn, party):
    rows = conn.execute(
        "SELECT repo, number FROM prs WHERE party = ? AND lifecycle NOT IN ('merged', 'closed')"
        " ORDER BY repo ASC, number ASC",
        (party,),
    ).fetchall()
    return ["{}#{}".format(row["repo"], row["number"]) for row in rows]


def close(ctx, name):
    party = _close_target(ctx, name)
    row = ctx.conn.execute(
        "SELECT project, generation, state FROM parties WHERE name = ?", (party,)
    ).fetchone()
    if row is None:
        raise GuildError("unknown party '{}'".format(party), 1)
    if row["state"] == "closed":
        raise GuildError("party '{}' is already closed".format(party), 1)
    summary = _cleanup_summary(ctx, party)
    open_prs = _open_pr_refs(ctx.conn, party)
    with db.writing(ctx.conn):
        events.record(
            ctx.conn,
            ctx.now,
            ctx.origin,
            party,
            ctx.session_id,
            row["project"],
            "party.closed",
            "local",
            {"party": party, "generation": row["generation"]},
        )
    lines = ["party '{}' closed: {}".format(party, summary)]
    if open_prs:
        lines.append("tracked PRs still open: {}".format(", ".join(open_prs)))
    return "\n".join(lines)
