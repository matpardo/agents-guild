import json

from guild import config, db, events, identity, pii, refs, sanitize, timeutil
from guild.ids import next_id
from guild.errors import GuildError


def _validate_scope(ctx, to):
    if to == "guild":
        return
    if not to.startswith("project:"):
        raise GuildError("invalid --to '{}': expected project:<name> or guild".format(to), 1)
    name = to[len("project:"):]
    config.load_project(ctx.projects_dir, name)


def create(ctx, text, to, ttl, until):
    _validate_scope(ctx, to)
    project = config.resolve_project(ctx.cwd, config.load_all_projects(ctx.projects_dir))
    patterns = pii.project_patterns(ctx.projects_dir, project)
    pii.validate_field(text, "notice text", pii.NOTICE_TEXT_MAX_LENGTH, patterns)
    expires_at = timeutil.expires_at_iso(ctx.now, ttl)
    until_condition = None
    if until is not None:
        until_condition = json.dumps(refs.parse_until(until))
    binding = identity.resolve_binding(ctx.conn, ctx.session_id)
    actor_party = binding["party"] if binding is not None else None
    notice_id = next_id(ctx.conn, "notices")
    with db.writing(ctx.conn):
        events.record(
            ctx.conn,
            ctx.now,
            ctx.origin,
            actor_party,
            ctx.session_id,
            project,
            "notice.created",
            "guild",
            {
                "id": notice_id,
                "party": actor_party,
                "scope": to,
                "text": text,
                "until_condition": until_condition,
                "expires_at": expires_at,
            },
        )
    return "notice #{} created\n{}".format(notice_id, pii.BROADCAST_REMINDER)


def close(ctx, notice_id):
    row = ctx.conn.execute("SELECT id, state FROM notices WHERE id = ?", (notice_id,)).fetchone()
    if row is None:
        raise GuildError("unknown notice #{}".format(notice_id), 1)
    if row["state"] != "active":
        raise GuildError("notice #{} is not active".format(notice_id), 1)
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
            "notice.closed",
            "guild",
            {"id": notice_id},
        )
    return "notice #{} closed".format(notice_id)


def active_notices(conn, now):
    rows = conn.execute("SELECT * FROM notices WHERE state = 'active'").fetchall()
    result = []
    for row in rows:
        if timeutil.is_expired(now, row["expires_at"]):
            continue
        result.append(row)
    return result


def format_notice_line(notice_id, party, text):
    author = party or "human"
    clean_text = sanitize.collapse_to_single_line(text)
    return '- notice #{} from {}: "{}"'.format(notice_id, author, clean_text)


def targeting(rows, project, scope_guild_always):
    matched = []
    for row in rows:
        if row["scope"] == "guild" and scope_guild_always:
            matched.append(row)
        elif project is not None and row["scope"] == "project:{}".format(project):
            matched.append(row)
    return matched


def list_active(ctx):
    rows = active_notices(ctx.conn, ctx.now)
    lines = []
    for row in rows:
        author = row["party"] or "human"
        lines.append("#{} [{}] {} ({})".format(row["id"], author, row["text"], row["scope"]))
    return lines
