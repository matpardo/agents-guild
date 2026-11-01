from guild import config, db, events, identity, names
from guild.commands import notice as notice_commands
from guild.commands import raid as raid_commands
from guild.errors import GuildError

_RESUME_NOTICE_TTL = "8h"
_HUMAN_LABEL = "human"


def _actor_party(ctx):
    if ctx.session_id is None:
        return None
    return identity.require_binding(ctx.conn, ctx.session_id)["party"]


def _authorize(ctx, raid_name, party):
    if party is None:
        raid_commands.require_active_raid(ctx.conn, ctx.now, raid_name)
        return
    _require_authorized_party(ctx, raid_name, party)


def _require_authorized_party(ctx, raid_name, party):
    members = raid_commands.require_active_raid(ctx.conn, ctx.now, raid_name)
    if party not in {row["party"] for row in members}:
        raise GuildError("party '{}' is not a member of raid '{}'".format(party, raid_name), 1)


def _append(ctx, party, kind, raid_name):
    project = config.resolve_project(ctx.cwd, config.load_all_projects(ctx.projects_dir))
    events.record(
        ctx.conn,
        ctx.now,
        ctx.origin,
        party,
        ctx.session_id,
        project,
        kind,
        "local",
        {"raid": raid_name, "party": party or _HUMAN_LABEL},
    )


def pause(ctx, raid_name):
    names.validate_name(raid_name, "raid name")
    party = _actor_party(ctx)
    with db.writing(ctx.conn):
        _authorize(ctx, raid_name, party)
        if raid_commands.is_paused(ctx.conn, raid_name):
            raise GuildError("raid '{}' is already paused".format(raid_name), 1)
        _append(ctx, party, "raid.paused", raid_name)
    return "raid '{}' paused".format(raid_name)


def resume(ctx, raid_name):
    names.validate_name(raid_name, "raid name")
    party = _actor_party(ctx)
    with db.writing(ctx.conn):
        _authorize(ctx, raid_name, party)
        if not raid_commands.is_paused(ctx.conn, raid_name):
            raise GuildError("raid '{}' is not paused".format(raid_name), 1)
        _append(ctx, party, "raid.resumed", raid_name)
        notice_commands.append_announcing(
            ctx,
            party,
            "raid {} resumed".format(raid_name),
            "raid:{}".format(raid_name),
            _RESUME_NOTICE_TTL,
            None,
        )
    return "raid '{}' resumed".format(raid_name)
