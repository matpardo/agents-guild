import json

from guild import config, db, events, identity, names, notices, pii, refs, sanitize, timeutil
from guild.commands import raid as raid_commands
from guild.errors import GuildError
from guild.ids import next_id

_PROJECT_SCOPE_PREFIX = "project:"


def _validate_scope(ctx, to):
    if to == "guild":
        return
    if to.startswith(_PROJECT_SCOPE_PREFIX):
        config.load_project(ctx.projects_dir, to[len(_PROJECT_SCOPE_PREFIX) :])
        return
    if to.startswith(notices.RAID_SCOPE_PREFIX):
        raid_name = to[len(notices.RAID_SCOPE_PREFIX) :]
        names.validate_name(raid_name, "raid name")
        raid_commands.require_active_raid(ctx.conn, ctx.now, raid_name)
        return
    raise GuildError("invalid --to '{}': expected project:<name>, raid:<name> or guild".format(to), 1)


def _reject_duplicate(ctx, actor_party, to, text):
    for row in notices.active_notices(ctx.conn, ctx.now):
        if row["party"] == actor_party and row["scope"] == to and row["text"] == text:
            raise GuildError("same text already active as notice #{}".format(row["id"]), 1)


def create(ctx, text, to, ttl, until):
    if text.strip() == "":
        raise GuildError("notice text must not be empty", 1)
    _validate_scope(ctx, to)
    project = config.resolve_project(ctx.cwd, config.load_all_projects(ctx.projects_dir))
    patterns = pii.project_patterns(ctx.projects_dir, project)
    pii.validate_field(text, "notice text", pii.NOTICE_TEXT_MAX_LENGTH, patterns)
    expires_at = timeutil.expires_at_iso(ctx.now, ttl)
    until_condition = None
    if until is not None:
        until_condition = json.dumps(refs.parse_until(until))
    actor_party, unbound = identity.resolve_actor(ctx.conn, ctx.session_id)
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
                "announces": None,
                "unbound": unbound,
            },
        )
    return "notice #{} created\n{}".format(notice_id, pii.BROADCAST_REMINDER)


def create_announcing(ctx, actor_party, text, to, ttl, announces):
    notice_id = next_id(ctx.conn, "notices")
    expires_at = timeutil.expires_at_iso(ctx.now, ttl)
    with db.writing(ctx.conn):
        events.record(
            ctx.conn,
            ctx.now,
            ctx.origin,
            actor_party,
            ctx.session_id,
            None,
            "notice.created",
            "guild",
            {
                "id": notice_id,
                "party": actor_party,
                "scope": to,
                "text": text,
                "until_condition": None,
                "expires_at": expires_at,
                "announces": announces,
            },
        )
    return notice_id


def announced(conn, announces):
    row = conn.execute("SELECT id FROM notices WHERE announces = ?", (announces,)).fetchone()
    return row is not None


def _record_notice_event(ctx, kind, notice_id):
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
            kind,
            "guild",
            {"id": notice_id},
        )


def _require_live_notice(ctx, notice_id):
    row = ctx.conn.execute("SELECT * FROM notices WHERE id = ?", (notice_id,)).fetchone()
    if row is None:
        raise GuildError("unknown notice #{}".format(notice_id), 1)
    if row["state"] != "active" or timeutil.is_expired(ctx.now, row["expires_at"]):
        raise GuildError("notice #{} is not active".format(notice_id), 1)
    return row


def close(ctx, notice_id):
    row = ctx.conn.execute("SELECT id, state FROM notices WHERE id = ?", (notice_id,)).fetchone()
    if row is None:
        raise GuildError("unknown notice #{}".format(notice_id), 1)
    if row["state"] != "active":
        raise GuildError("notice #{} is not active".format(notice_id), 1)
    _record_notice_event(ctx, "notice.closed", notice_id)
    return "notice #{} closed".format(notice_id)


def mark_seen(ctx, notice_id):
    row = _require_live_notice(ctx, notice_id)
    if row["seen_at"] is not None:
        raise GuildError("notice #{} is already seen".format(notice_id), 1)
    _record_notice_event(ctx, "notice.seen", notice_id)
    return "notice #{} seen".format(notice_id)


def mark_unseen(ctx, notice_id):
    row = _require_live_notice(ctx, notice_id)
    if row["seen_at"] is None:
        raise GuildError("notice #{} is not seen".format(notice_id), 1)
    _record_notice_event(ctx, "notice.unseen", notice_id)
    return "notice #{} unseen".format(notice_id)


def mark_all_seen(ctx):
    unseen = [row for row in notices.active_notices(ctx.conn, ctx.now) if row["seen_at"] is None]
    for row in unseen:
        _record_notice_event(ctx, "notice.seen", row["id"])
    return "{} notices marked seen".format(len(unseen))


def is_new(row):
    return row["seen_at"] is None


def count_new(rows):
    return len([row for row in rows if is_new(row)])


def format_notice_line(notice_id, party, issued_at, text, unbound):
    author = identity.actor_label(party, unbound)
    clean_text = sanitize.escape_quotes(sanitize.collapse_to_single_line(text))
    line = '- notice #{} from {} at {}: "{}"'.format(notice_id, author, timeutil.issued_label(issued_at), clean_text)
    if author != identity.HUMAN_LABEL and pii.looks_instruction_like(text):
        return "{} {}".format(line, pii.INSTRUCTION_LIKE_FLAG)
    return line


def _list_line(ctx, row):
    author = identity.actor_label(row["party"], bool(row["unbound"]))
    prefix = "new " if is_new(row) else ""
    return "{}#{} [{}] {} ({}, {}, {})".format(
        prefix,
        row["id"],
        author,
        row["text"],
        row["scope"],
        timeutil.issued_label(row["created_at"]),
        timeutil.time_left_label(ctx.now, row["expires_at"]),
    )


def list_active(ctx):
    rows = notices.active_notices(ctx.conn, ctx.now)
    lines = [_list_line(ctx, row) for row in rows]
    new_count = count_new(rows)
    if new_count > 0:
        lines.append("{} new".format(new_count))
    return lines
