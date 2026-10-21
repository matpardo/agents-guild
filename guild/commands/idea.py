import datetime

from guild import config, db, events, identity, pii
from guild.errors import GuildError
from guild.ids import next_id

_REQUIRED_TEXT_LIMITS = {
    "title": pii.IDEA_TITLE_MAX_LENGTH,
    "description": pii.IDEA_DESCRIPTION_MAX_LENGTH,
}
_OPTIONAL_TEXT_LIMITS = {"requester": pii.IDEA_REQUESTER_MAX_LENGTH}


def _validate_deadline(deadline):
    if deadline is None:
        return
    try:
        datetime.date.fromisoformat(deadline)
    except ValueError:
        raise GuildError("deadline must be a date like 2026-12-31", 1)


def _validate_project(ctx, project):
    if project is None:
        return
    config.load_project(ctx.projects_dir, project)


def _validate_text(ctx, name, value, project):
    if name in _REQUIRED_TEXT_LIMITS and (value is None or value.strip() == ""):
        raise GuildError("idea {} must not be empty".format(name), 1)
    if value is None:
        return
    limit = _REQUIRED_TEXT_LIMITS.get(name, _OPTIONAL_TEXT_LIMITS.get(name))
    pii.validate_field(value, "idea " + name, limit, pii.project_patterns(ctx.projects_dir, project))


def _validate_fields(ctx, fields, project):
    _validate_deadline(fields.get("deadline"))
    _validate_project(ctx, fields.get("project"))
    for name in ("title", "description", "requester"):
        if name in fields:
            _validate_text(ctx, name, fields[name], project)


def _record(ctx, kind, payload):
    binding = identity.resolve_binding(ctx.conn, ctx.session_id)
    actor_party = binding["party"] if binding is not None else None
    project = config.resolve_project(ctx.cwd, config.load_all_projects(ctx.projects_dir))
    with db.writing(ctx.conn):
        events.record(
            ctx.conn, ctx.now, ctx.origin, actor_party, ctx.session_id, project, kind, "local", payload
        )


def _require_idea(ctx, idea_id):
    row = ctx.conn.execute("SELECT * FROM ideas WHERE id = ?", (idea_id,)).fetchone()
    if row is None:
        raise GuildError("unknown idea #{}".format(idea_id), 1)
    return row


def add(ctx, title, description, requester, deadline, project):
    fields = {
        "title": title,
        "description": description,
        "requester": requester,
        "deadline": deadline,
        "project": project,
    }
    _validate_fields(ctx, fields, project)
    idea_id = next_id(ctx.conn, "ideas")
    _record(ctx, "idea.created", dict(fields, id=idea_id))
    return "idea #{} added".format(idea_id)


def edit(ctx, idea_id, fields):
    if not fields:
        raise GuildError("nothing to edit: pass at least one field", 1)
    row = _require_idea(ctx, idea_id)
    _validate_fields(ctx, fields, fields.get("project", row["project"]))
    _record(ctx, "idea.edited", {"id": idea_id, "fields": fields})
    return "idea #{} edited".format(idea_id)


def delete(ctx, idea_id):
    _require_idea(ctx, idea_id)
    _record(ctx, "idea.deleted", {"id": idea_id})
    return "idea #{} deleted".format(idea_id)


def is_overdue(now, deadline):
    return deadline is not None and deadline < now.date().isoformat()


def sorted_rows(ctx, project):
    rows = ctx.conn.execute("SELECT * FROM ideas ORDER BY created_at ASC, id ASC").fetchall()
    if project is not None:
        rows = [row for row in rows if row["project"] == project]
    return sorted(rows, key=lambda row: (row["deadline"] is None, row["deadline"] or ""))


def _list_line(ctx, row):
    parts = [row["project"], "due " + row["deadline"] if row["deadline"] else None]
    if is_overdue(ctx.now, row["deadline"]):
        parts.append("overdue")
    label = ", ".join(part for part in parts if part is not None)
    suffix = " ({})".format(label) if label else ""
    return "#{} {}{}".format(row["id"], row["title"], suffix)


def list_ideas(ctx, project):
    rows = sorted_rows(ctx, project)
    if not rows:
        return ["no ideas"]
    return [_list_line(ctx, row) for row in rows]


def show(ctx, idea_id):
    row = _require_idea(ctx, idea_id)
    lines = ["#{} {}".format(row["id"], row["title"]), row["description"]]
    for label in ("requester", "deadline", "project"):
        if row[label] is not None:
            lines.append("{}: {}".format(label, row[label]))
    if is_overdue(ctx.now, row["deadline"]):
        lines.append("overdue")
    lines.append("created: {}".format(row["created_at"]))
    return lines
