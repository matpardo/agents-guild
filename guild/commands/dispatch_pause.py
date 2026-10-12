from guild import config, db, events, identity, pii
from guild.errors import GuildError

_HUMAN_LABEL = "human"
_UNBOUND_SESSION_LABEL = "session"


def current(conn):
    row = conn.execute("SELECT * FROM dispatch_pause WHERE id = 1").fetchone()
    if row is None:
        return None
    return dict(row)


def _actor(ctx):
    if ctx.session_id is None:
        return None, _HUMAN_LABEL
    binding = identity.resolve_binding(ctx.conn, ctx.session_id)
    if binding is not None:
        return binding["party"], binding["party"]
    return None, _UNBOUND_SESSION_LABEL


def _validate_reason(ctx, reason):
    if reason.strip() == "":
        raise GuildError("pause reason must not be empty", 1)
    project = config.resolve_project(ctx.cwd, config.load_all_projects(ctx.projects_dir))
    patterns = pii.project_patterns(ctx.projects_dir, project)
    pii.validate_field(reason, "pause reason", pii.DISPATCH_PAUSE_REASON_MAX_LENGTH, patterns)


def _record(ctx, party, kind, payload):
    with db.writing(ctx.conn):
        events.record(ctx.conn, ctx.now, ctx.origin, party, ctx.session_id, None, kind, "local", payload)


def pause(ctx, reason):
    if current(ctx.conn) is not None:
        raise GuildError("dispatch is already paused", 1)
    _validate_reason(ctx, reason)
    party, actor = _actor(ctx)
    _record(ctx, party, "dispatch.paused", {"reason": reason, "party": actor})
    return "dispatch paused: {}".format(reason)


def resume(ctx):
    if ctx.session_id is not None:
        raise GuildError("dispatch resume must be run by a human, outside a session", 1)
    if current(ctx.conn) is None:
        raise GuildError("dispatch is not paused", 1)
    _record(ctx, None, "dispatch.resumed", {})
    return "dispatch resumed"
