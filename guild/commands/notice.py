import json

from guild import config, db, events, identity, names, pii, refs, sanitize, timeutil
from guild.commands import raid as raid_commands
from guild.ids import next_id
from guild.errors import GuildError

_PROJECT_SCOPE_PREFIX = "project:"
_RAID_SCOPE_PREFIX = "raid:"


def _validate_scope(ctx, to):
    if to == "guild":
        return
    if to.startswith(_PROJECT_SCOPE_PREFIX):
        config.load_project(ctx.projects_dir, to[len(_PROJECT_SCOPE_PREFIX):])
        return
    if to.startswith(_RAID_SCOPE_PREFIX):
        raid_name = to[len(_RAID_SCOPE_PREFIX):]
        names.validate_name(raid_name, "raid name")
        if not raid_commands.active_members(ctx.conn, ctx.now, raid_name):
            raise GuildError("raid '{}' has no active members".format(raid_name), 1)
        return
    raise GuildError(
        "invalid --to '{}': expected project:<name>, raid:<name> or guild".format(to), 1
    )


def _reject_duplicate(ctx, actor_party, to, text):
    for row in active_notices(ctx.conn, ctx.now):
        if row["party"] == actor_party and row["scope"] == to and row["text"] == text:
            raise GuildError("same text already active as notice #{}".format(row["id"]), 1)


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
    _reject_duplicate(ctx, actor_party, to, text)
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


def targeting(rows, project, scope_guild_always, raid_member_of):
    matched = []
    for row in rows:
        if row["scope"] == "guild" and scope_guild_always:
            matched.append(row)
        elif project is not None and row["scope"] == "project:{}".format(project):
            matched.append(row)
        elif row["scope"].startswith(_RAID_SCOPE_PREFIX) and row["scope"][len(_RAID_SCOPE_PREFIX):] in raid_member_of:
            matched.append(row)
    return matched


def list_active(ctx):
    rows = active_notices(ctx.conn, ctx.now)
    lines = []
    for row in rows:
        author = row["party"] or "human"
        lines.append("#{} [{}] {} ({})".format(row["id"], author, row["text"], row["scope"]))
    return lines
