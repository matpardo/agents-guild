from pathlib import Path

from guild import config, db, events, identity, session_info
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


def resume(ctx, name):
    if ctx.session_id is None:
        raise GuildError("party resume requires a Claude Code session", 1)
    row = ctx.conn.execute(
        "SELECT project, generation, state FROM parties WHERE name = ?", (name,)
    ).fetchone()
    if row is None:
        raise GuildError("unknown party '{}'".format(name), 1)
    if row["state"] == "closed":
        raise GuildError("party '{}' is closed".format(name), 1)
    generation = row["generation"] + 1
    session_name = session_info.read_session_name(ctx.sessions_dir, ctx.session_id)
    with db.writing(ctx.conn):
        events.record(
            ctx.conn,
            ctx.now,
            ctx.origin,
            name,
            ctx.session_id,
            row["project"],
            "party.resumed",
            "local",
            {"party": name, "generation": generation, "session_name": session_name},
        )
    lines = ["party '{}' resumed, generation {}".format(name, generation)]
    handoff_content = previous_handoff_content(ctx.conn, name, generation)
    if handoff_content is not None:
        lines += ["", handoff_content, ""]
        lines.extend(next_commands.run(ctx, False, False))
    return "\n".join(lines)


def close(ctx):
    binding = identity.require_binding(ctx.conn, ctx.session_id)
    with db.writing(ctx.conn):
        events.record(
            ctx.conn,
            ctx.now,
            ctx.origin,
            binding["party"],
            ctx.session_id,
            binding["project"],
            "party.closed",
            "local",
            {"party": binding["party"], "generation": binding["generation"]},
        )
    return "party '{}' closed".format(binding["party"])
