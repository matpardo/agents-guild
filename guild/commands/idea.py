import datetime

from guild import config, db, events, identity, pii, timeutil
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
        raise GuildError("deadline must be a date like 2026-12-31", 1) from None


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
    actor_party, _ = identity.resolve_actor(ctx.conn, ctx.session_id)
    project = config.resolve_project(ctx.cwd, config.load_all_projects(ctx.projects_dir))
    with db.writing(ctx.conn):
        events.record(ctx.conn, ctx.now, ctx.origin, actor_party, ctx.session_id, project, kind, "local", payload)


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


def _require_open_party(ctx, party):
    row = ctx.conn.execute("SELECT state FROM parties WHERE name = ?", (party,)).fetchone()
    if row is None:
        raise GuildError("unknown party '{}'".format(party), 1)
    if row["state"] == "closed":
        raise GuildError("party '{}' is closed".format(party), 1)


def _is_linked(ctx, idea_id, party):
    row = ctx.conn.execute("SELECT 1 FROM idea_links WHERE idea_id = ? AND party = ?", (idea_id, party)).fetchone()
    return row is not None


def link_for_party(ctx, idea_id, party):
    _require_idea(ctx, idea_id)
    _require_open_party(ctx, party)
    if _is_linked(ctx, idea_id, party):
        raise GuildError("idea #{} is already linked to party '{}'".format(idea_id, party), 1)
    _record(ctx, "idea.linked", {"id": idea_id, "party": party})
    return "idea #{} linked to party '{}'".format(idea_id, party)


def unlink_for_party(ctx, idea_id, party):
    _require_idea(ctx, idea_id)
    link_row = next((row for row in linked_parties(ctx, idea_id) if row["name"] == party), None)
    if link_row is None:
        raise GuildError("idea #{} is not linked to party '{}'".format(idea_id, party), 1)
    if link_row["has_prs"]:
        raise GuildError("idea #{} stays linked to party '{}': the party already tracks a PR".format(idea_id, party), 1)
    _record(ctx, "idea.unlinked", {"id": idea_id, "party": party})
    return "idea #{} unlinked from party '{}'".format(idea_id, party)


def _resolve_party(ctx, party):
    if ctx.session_id is None:
        if party is None:
            raise GuildError("pass --party <name>: no session to take the party from", 1)
        return party
    own_party = identity.require_binding(ctx.conn, ctx.session_id)["party"]
    if party is not None and party != own_party:
        raise GuildError("a session acts only for its own party '{}'".format(own_party), 1)
    return own_party


def link(ctx, idea_id, party):
    return link_for_party(ctx, idea_id, _resolve_party(ctx, party))


def unlink(ctx, idea_id, party):
    return unlink_for_party(ctx, idea_id, _resolve_party(ctx, party))


def linked_parties(ctx, idea_id):
    return ctx.conn.execute(
        "SELECT idea_links.party AS name, COALESCE(parties.state, 'closed') AS state,"
        " EXISTS (SELECT 1 FROM prs WHERE prs.party = idea_links.party) AS has_prs"
        " FROM idea_links LEFT JOIN parties ON parties.name = idea_links.party"
        " WHERE idea_links.idea_id = ? ORDER BY idea_links.linked_at ASC, idea_links.party ASC",
        (idea_id,),
    ).fetchall()


def _worked_by(ctx, idea_id):
    parties = linked_parties(ctx, idea_id)
    if not parties:
        return ["not linked yet"]
    labels = [row["name"] + (" (closed)" if row["state"] == "closed" else "") for row in parties]
    return ["worked by: " + ", ".join(labels)]


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
    return ["#{} {}{}".format(row["id"], row["title"], suffix)] + ["  " + line for line in _worked_by(ctx, row["id"])]


def list_ideas(ctx, project):
    rows = sorted_rows(ctx, project)
    if not rows:
        return ["no ideas"]
    return [line for row in rows for line in _list_line(ctx, row)]


def show(ctx, idea_id):
    row = _require_idea(ctx, idea_id)
    lines = ["#{} {}".format(row["id"], row["title"]), row["description"]]
    for label in ("requester", "deadline", "project"):
        if row[label] is not None:
            lines.append("{}: {}".format(label, row[label]))
    if is_overdue(ctx.now, row["deadline"]):
        lines.append("overdue")
    lines.extend(_worked_by(ctx, idea_id))
    lines.append(timeutil.dates_label(row["created_at"], row["updated_at"]))
    return lines
