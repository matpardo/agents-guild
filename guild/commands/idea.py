import datetime
import json
import os
import re
import uuid
from pathlib import Path

from guild import config, db, events, identity, pii, timeutil
from guild.errors import GuildError
from guild.ids import next_id
from guild.realm import hub

_EXPORT_FORMAT = "idea-export/1"
_RECEIPT_FORMAT = "idea-receipt/1"
_DESTINATION_MAX_LENGTH = 100
_ENTRY_KEYS = {"uuid", "title", "description", "deadline", "project"}
_FENCE_RE = re.compile(r"```json\n(.*?)\n```", re.DOTALL)

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


def _append(ctx, kind, payload):
    actor_party, _ = identity.resolve_actor(ctx.conn, ctx.session_id)
    project = config.resolve_project(ctx.cwd, config.load_all_projects(ctx.projects_dir))
    events.record(ctx.conn, ctx.now, ctx.origin, actor_party, ctx.session_id, project, kind, "local", payload)


def _record(ctx, kind, payload):
    with db.writing(ctx.conn):
        _append(ctx, kind, payload)


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
    with db.writing(ctx.conn):
        idea_id = next_id(ctx.conn, "ideas")
        _append(ctx, "idea.created", dict(fields, id=idea_id))
    return "idea #{} added".format(idea_id)


def edit(ctx, idea_id, fields):
    if not fields:
        raise GuildError("nothing to edit: pass at least one field", 1)
    row = _require_idea(ctx, idea_id)
    _validate_fields(ctx, fields, fields.get("project", row["project"]))
    with db.writing(ctx.conn):
        _require_idea(ctx, idea_id)
        _append(ctx, "idea.edited", {"id": idea_id, "fields": fields})
    return "idea #{} edited".format(idea_id)


def delete(ctx, idea_id):
    with db.writing(ctx.conn):
        _require_idea(ctx, idea_id)
        _append(ctx, "idea.deleted", {"id": idea_id})
    return "idea #{} deleted".format(idea_id)


def _require_not_exported(row):
    if row["exported_at"] is not None:
        raise GuildError("idea #{} is exported to {}: unexport it first".format(row["id"], row["exported_to"]), 1)


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
    with db.writing(ctx.conn):
        _require_not_exported(_require_idea(ctx, idea_id))
        _require_open_party(ctx, party)
        if _is_linked(ctx, idea_id, party):
            raise GuildError("idea #{} is already linked to party '{}'".format(idea_id, party), 1)
        _append(ctx, "idea.linked", {"id": idea_id, "party": party})
    return "idea #{} linked to party '{}'".format(idea_id, party)


def unlink_for_party(ctx, idea_id, party):
    with db.writing(ctx.conn):
        _require_idea(ctx, idea_id)
        link_row = next((row for row in linked_parties(ctx, idea_id) if row["name"] == party), None)
        if link_row is None:
            raise GuildError("idea #{} is not linked to party '{}'".format(idea_id, party), 1)
        if link_row["has_prs"]:
            raise GuildError(
                "idea #{} stays linked to party '{}': the party already tracks a PR".format(idea_id, party), 1
            )
        _append(ctx, "idea.unlinked", {"id": idea_id, "party": party})
    return "idea #{} unlinked from party '{}'".format(idea_id, party)


def _require_active_adventurer(ctx, adventurer):
    row = ctx.conn.execute("SELECT state FROM adventurers WHERE id = ?", (adventurer,)).fetchone()
    if row is None:
        raise GuildError("unknown adventurer {}".format(adventurer), 1)
    if row["state"] != "active":
        raise GuildError("adventurer {} is {}".format(adventurer, row["state"]), 1)


def link_for_adventurer(ctx, idea_id, adventurer):
    with db.writing(ctx.conn):
        _require_not_exported(_require_idea(ctx, idea_id))
        _require_active_adventurer(ctx, adventurer)
        if any(row["id"] == adventurer for row in linked_adventurers(ctx, idea_id)):
            raise GuildError("idea #{} is already linked to adventurer {}".format(idea_id, adventurer), 1)
        _append(ctx, "idea.adventurer_linked", {"id": idea_id, "adventurer": adventurer})
    return "idea #{} linked to adventurer {}".format(idea_id, adventurer)


def unlink_for_adventurer(ctx, idea_id, adventurer):
    with db.writing(ctx.conn):
        _require_idea(ctx, idea_id)
        link_row = next((row for row in linked_adventurers(ctx, idea_id) if row["id"] == adventurer), None)
        if link_row is None:
            raise GuildError("idea #{} is not linked to adventurer {}".format(idea_id, adventurer), 1)
        if link_row["has_prs"]:
            raise GuildError(
                "idea #{} stays linked to adventurer {}: the adventurer already tracks a PR".format(
                    idea_id, adventurer
                ),
                1,
            )
        _append(ctx, "idea.adventurer_unlinked", {"id": idea_id, "adventurer": adventurer})
    return "idea #{} unlinked from adventurer {}".format(idea_id, adventurer)


def _resolve_holder(ctx, party, adventurer):
    if ctx.session_id is None:
        if (party is None) == (adventurer is None):
            raise GuildError("pass --party <name> or --adventurer <id>: no session to take the holder from", 1)
        return ("party", party) if party is not None else ("adventurer", adventurer)
    own_adventurer = identity.resolve_adventurer(ctx.conn, ctx.session_id)
    if own_adventurer is not None:
        if party is not None:
            raise GuildError("a session acts only for its own adventurer {}".format(own_adventurer["id"]), 1)
        if adventurer is not None and adventurer != own_adventurer["id"]:
            raise GuildError("a session acts only for its own adventurer {}".format(own_adventurer["id"]), 1)
        return ("adventurer", own_adventurer["id"])
    own_party = identity.require_binding(ctx.conn, ctx.session_id)["party"]
    if adventurer is not None:
        raise GuildError("a session acts only for its own party '{}'".format(own_party), 1)
    if party is not None and party != own_party:
        raise GuildError("a session acts only for its own party '{}'".format(own_party), 1)
    return ("party", own_party)


def link(ctx, idea_id, party, adventurer):
    kind, holder = _resolve_holder(ctx, party, adventurer)
    if kind == "adventurer":
        return link_for_adventurer(ctx, idea_id, holder)
    return link_for_party(ctx, idea_id, holder)


def unlink(ctx, idea_id, party, adventurer):
    kind, holder = _resolve_holder(ctx, party, adventurer)
    if kind == "adventurer":
        return unlink_for_adventurer(ctx, idea_id, holder)
    return unlink_for_party(ctx, idea_id, holder)


def linked_parties(ctx, idea_id):
    return ctx.conn.execute(
        "SELECT idea_links.party AS name, COALESCE(parties.state, 'closed') AS state,"
        " EXISTS (SELECT 1 FROM prs WHERE prs.party = idea_links.party) AS has_prs"
        " FROM idea_links LEFT JOIN parties ON parties.name = idea_links.party"
        " WHERE idea_links.idea_id = ? ORDER BY idea_links.linked_at ASC, idea_links.party ASC",
        (idea_id,),
    ).fetchall()


def linked_adventurers(ctx, idea_id):
    return ctx.conn.execute(
        "SELECT idea_adventurer_links.adventurer AS id, COALESCE(adventurers.state, 'dismissed') AS state,"
        " EXISTS (SELECT 1 FROM prs WHERE prs.adventurer = idea_adventurer_links.adventurer) AS has_prs"
        " FROM idea_adventurer_links LEFT JOIN adventurers ON adventurers.id = idea_adventurer_links.adventurer"
        " WHERE idea_adventurer_links.idea_id = ?"
        " ORDER BY idea_adventurer_links.linked_at ASC, idea_adventurer_links.adventurer ASC",
        (idea_id,),
    ).fetchall()


def _worked_by(ctx, idea_id):
    parties = linked_parties(ctx, idea_id)
    adventurers = linked_adventurers(ctx, idea_id)
    if not parties and not adventurers:
        return ["not linked yet"]
    labels = [row["name"] + (" (closed)" if row["state"] == "closed" else "") for row in parties]
    labels.extend(
        identity.adventurer_label(row["id"]) + ("" if row["state"] == "active" else " ({})".format(row["state"]))
        for row in adventurers
    )
    return ["worked by: " + ", ".join(labels)]


def is_overdue(now, deadline):
    return deadline is not None and deadline < now.date().isoformat()


def sorted_rows(ctx, project, exported):
    rows = ctx.conn.execute("SELECT * FROM ideas ORDER BY created_at ASC, id ASC").fetchall()
    rows = [row for row in rows if (row["exported_at"] is not None) == exported]
    if project is not None:
        rows = [row for row in rows if row["project"] == project]
    return sorted(rows, key=lambda row: (row["deadline"] is None, row["deadline"] or ""))


def _list_line(ctx, row):
    parts = [
        row["project"],
        "due " + row["deadline"] if row["deadline"] else None,
        "exported to " + row["exported_to"] if row["exported_at"] is not None else None,
    ]
    if is_overdue(ctx.now, row["deadline"]):
        parts.append("overdue")
    label = ", ".join(part for part in parts if part is not None)
    suffix = " ({})".format(label) if label else ""
    return ["#{} {}{}".format(row["id"], row["title"], suffix)] + ["  " + line for line in _worked_by(ctx, row["id"])]


def list_ideas(ctx, project, exported):
    rows = sorted_rows(ctx, project, exported)
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


def _require_human(ctx, action):
    if ctx.session_id is not None:
        raise GuildError(
            "idea {} runs from the human terminal or the web board, not inside a Claude Code session".format(action), 1
        )


def _checked_target(path, flag):
    target = Path(path)
    if target.suffix != ".md":
        raise GuildError("{} must end in .md".format(flag), 1)
    if target.exists():
        raise GuildError("{} already exists: {}".format(flag, target), 1)
    return target


def _render_document(title, payload):
    return "# {}\n\n```json\n{}\n```\n".format(title, json.dumps(payload, indent=2, ensure_ascii=False))


def _check_size(text):
    if len(text.encode("utf-8")) > hub.CONTENT_MAX_BYTES:
        raise GuildError("content too large: limit is {} bytes".format(hub.CONTENT_MAX_BYTES), 1)


def _write_new(target, text):
    try:
        descriptor = os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except OSError as error:
        raise GuildError("cannot write {}: {}".format(target, error), 1) from error
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(text)


def _parse_document(text, expected_format):
    _check_size(text)
    match = _FENCE_RE.search(text)
    if match is None:
        raise GuildError("no json block found: expected a {} file".format(expected_format), 1)
    try:
        data = json.loads(match.group(1))
    except ValueError as error:
        raise GuildError("invalid json block: {}".format(error), 1) from error
    if not isinstance(data, dict) or data.get("format") != expected_format:
        raise GuildError("unsupported format: expected {}".format(expected_format), 1)
    return data


def _is_uuid(value):
    if not isinstance(value, str):
        return False
    try:
        return str(uuid.UUID(value)) == value
    except ValueError:
        return False


def _is_blocked_by_link(ctx, idea_id):
    return any(row["state"] != "closed" for row in linked_parties(ctx, idea_id)) or any(
        row["state"] == "active" for row in linked_adventurers(ctx, idea_id)
    )


def _validate_destination(ctx, destination):
    if destination.strip() == "":
        raise GuildError("--to must not be empty", 1)
    pii.validate_field(destination, "destination", _DESTINATION_MAX_LENGTH, [])


def _select_by_ids(ctx, idea_ids):
    rows = []
    for idea_id in dict.fromkeys(idea_ids):
        row = _require_idea(ctx, idea_id)
        if row["exported_at"] is not None:
            raise GuildError("idea #{} is already exported to {}".format(idea_id, row["exported_to"]), 1)
        if _is_blocked_by_link(ctx, idea_id):
            raise GuildError("idea #{} is linked to an open party or an active adventurer".format(idea_id), 1)
        rows.append(row)
    return rows, []


def _select_by_project(ctx, project):
    _validate_project(ctx, project)
    candidates = ctx.conn.execute(
        "SELECT * FROM ideas WHERE project = ? AND exported_at IS NULL ORDER BY id ASC", (project,)
    ).fetchall()
    rows = []
    skipped = []
    for row in candidates:
        if _is_blocked_by_link(ctx, row["id"]):
            skipped.append("skipped #{}: linked to an open party or an active adventurer".format(row["id"]))
            continue
        rows.append(row)
    if not rows:
        raise GuildError("no exportable idea in project '{}'".format(project), 1)
    return rows, skipped


def _entry(row, idea_uuid):
    return {
        "uuid": idea_uuid,
        "title": row["title"],
        "description": row["description"],
        "deadline": row["deadline"],
        "project": row["project"],
    }


def _export(ctx, select, destination, out):
    _require_human(ctx, "export")
    _validate_destination(ctx, destination)
    target = _checked_target(out, "--out")
    with db.writing(ctx.conn):
        rows, skipped = select(ctx)
        entries = []
        for row in rows:
            idea_uuid = row["uuid"] or str(uuid.uuid4())
            _append(ctx, "idea.exported", {"id": row["id"], "uuid": idea_uuid, "destination": destination})
            entries.append(_entry(row, idea_uuid))
        text = _render_document("Idea export", {"format": _EXPORT_FORMAT, "ideas": entries})
        _check_size(text)
        _write_new(target, text)
    lines = ["exported {} ideas to {}: {}".format(len(rows), destination, target)]
    lines.extend(skipped)
    lines.append("requester and links are not exported; confirm with the receipt from the other side")
    return "\n".join(lines)


def export_ids(ctx, idea_ids, destination, out):
    return _export(ctx, lambda inner: _select_by_ids(inner, idea_ids), destination, out)


def export_project(ctx, project, destination, out):
    return _export(ctx, lambda inner: _select_by_project(inner, project), destination, out)


def unexport(ctx, idea_id):
    _require_human(ctx, "unexport")
    with db.writing(ctx.conn):
        row = _require_idea(ctx, idea_id)
        if row["exported_at"] is None:
            raise GuildError("idea #{} is not exported".format(idea_id), 1)
        _append(ctx, "idea.unexported", {"id": idea_id})
    return "idea #{} is back in the list; if {} already imported it, both guilds now hold it".format(
        idea_id, row["exported_to"]
    )


def _entry_fields(entry, project):
    if not isinstance(entry, dict) or set(entry) != _ENTRY_KEYS:
        raise GuildError("each idea needs exactly the keys: {}".format(", ".join(sorted(_ENTRY_KEYS))), 1)
    if not _is_uuid(entry["uuid"]):
        raise GuildError("invalid idea uuid: {!r}".format(entry["uuid"]), 1)
    for name in ("title", "description"):
        if not isinstance(entry[name], str):
            raise GuildError("idea {} must be text".format(name), 1)
    for name in ("deadline", "project"):
        if entry[name] is not None and not isinstance(entry[name], str):
            raise GuildError("idea {} must be text or null".format(name), 1)
    return {
        "title": entry["title"],
        "description": entry["description"],
        "requester": None,
        "deadline": entry["deadline"],
        "project": project if project is not None else entry["project"],
    }


def import_text(ctx, text, receipt, project):
    _require_human(ctx, "import")
    target = _checked_target(receipt, "--receipt")
    entries = _parse_document(text, _EXPORT_FORMAT).get("ideas")
    if not isinstance(entries, list) or not entries:
        raise GuildError("the file holds no ideas", 1)
    if project is not None:
        _validate_project(ctx, project)
    imported = []
    skipped = []
    live_uuids = []
    flagged = []
    with db.writing(ctx.conn):
        for entry in entries:
            fields = _entry_fields(entry, project)
            _validate_fields(ctx, fields, fields["project"])
            existing = ctx.conn.execute("SELECT id, exported_at FROM ideas WHERE uuid = ?", (entry["uuid"],)).fetchone()
            if existing is not None:
                if existing["exported_at"] is None:
                    live_uuids.append(entry["uuid"])
                    skipped.append("skipped {}: already here as #{}".format(entry["uuid"], existing["id"]))
                    continue
                skipped.append(
                    "skipped {}: it is exported from here as #{}; run 'idea unexport {}' to take it back".format(
                        entry["uuid"], existing["id"], existing["id"]
                    )
                )
                continue
            idea_id = next_id(ctx.conn, "ideas")
            _append(ctx, "idea.imported", dict(fields, id=idea_id, uuid=entry["uuid"]))
            imported.append(idea_id)
            live_uuids.append(entry["uuid"])
            if pii.looks_instruction_like(fields["title"] + "\n" + fields["description"]):
                flagged.append("#{} {}".format(idea_id, pii.INSTRUCTION_LIKE_FLAG))
        receipt_text = _render_document(
            "Idea receipt", {"format": _RECEIPT_FORMAT, "uuids": list(dict.fromkeys(live_uuids))}
        )
        _write_new(target, receipt_text)
    lines = ["imported {} ideas: {}".format(len(imported), ", ".join("#{}".format(i) for i in imported) or "none")]
    lines.extend(skipped)
    lines.extend(flagged)
    lines.append("receipt written to {}: carry it back to the sender and run 'idea confirm-export'".format(target))
    return "\n".join(lines)


def confirm_export_text(ctx, text):
    _require_human(ctx, "confirm-export")
    uuids = _parse_document(text, _RECEIPT_FORMAT).get("uuids")
    if not isinstance(uuids, list) or not all(_is_uuid(value) for value in uuids):
        raise GuildError("the receipt needs a list of uuids", 1)
    deleted = []
    ignored = []
    with db.writing(ctx.conn):
        for value in uuids:
            row = ctx.conn.execute("SELECT id, exported_at FROM ideas WHERE uuid = ?", (value,)).fetchone()
            if row is None or row["exported_at"] is None:
                ignored.append(value)
                continue
            _append(ctx, "idea.deleted", {"id": row["id"]})
            deleted.append(row["id"])
    lines = [
        "deleted {} exported ideas: {}".format(len(deleted), ", ".join("#{}".format(i) for i in deleted) or "none")
    ]
    lines.extend("ignored {}: unknown here or not exported".format(value) for value in ignored)
    return "\n".join(lines)
