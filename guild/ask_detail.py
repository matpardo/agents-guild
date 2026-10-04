import json
from pathlib import Path

from guild import links, paths, resume, sanitize, task_context, timeutil
from guild.commands import ask as ask_commands
from guild.commands import party as party_commands
from guild.commands import revive

_EVENT_KINDS = (
    "quest.added",
    "quest.done",
    "task.added",
    "task.started",
    "task.blocked",
    "task.done",
    "pr.tracked",
    "pr.set",
    "ask.created",
    "ask.answered",
    "party.handed_off",
    "party.closed",
)
_EVENT_LIMIT = 10
_NOT_FOUND = "(not found)"


def _card_ref(ctx, project, project_config, ref):
    key = ref[len("card:"):]
    row = None
    if project is not None:
        row = ctx.conn.execute(
            "SELECT status FROM cards WHERE project = ? AND key = ?", (project, key)
        ).fetchone()
    if row is None and not ask_commands.card_known(ctx, project, project_config, key):
        return {"kind": "card", "ref": ref, "key": key, "missing": True}
    return {
        "kind": "card",
        "ref": ref,
        "key": key,
        "status": None if row is None else row["status"],
        "url": links.card_url(project_config, key),
    }


def _pr_ref(ctx, ref):
    repo, number = ref[len("pr:"):].rsplit("#", 1)
    row = ctx.conn.execute(
        "SELECT lifecycle, waits, checks_failing, checks_passing, checks_pending FROM prs"
        " WHERE repo = ? AND number = ?",
        (repo, int(number)),
    ).fetchone()
    url = links.pr_url(repo, int(number))
    if row is None:
        return {"kind": "pr", "ref": ref, "url": url, "missing": True}
    return {
        "kind": "pr",
        "ref": ref,
        "url": url,
        "lifecycle": row["lifecycle"],
        "checks_failing": row["checks_failing"] or 0,
        "checks_passing": row["checks_passing"] or 0,
        "checks_pending": row["checks_pending"] or 0,
        "waits": row["waits"],
    }


def _expand_ref(ctx, project, project_config, ref):
    if ref.startswith("pr:"):
        return _pr_ref(ctx, ref)
    if ref.startswith("card:"):
        return _card_ref(ctx, project, project_config, ref)
    return task_context.task_ref(ctx, project_config, ref)


def _origin(ask_row):
    if ask_row["snapshot"] is None:
        return None
    return json.loads(ask_row["snapshot"])


def _resume(ctx, ask_row, origin):
    if origin is None or origin.get("session_id") is None:
        return None
    session_id = origin["session_id"]
    leader = ctx.conn.execute(
        "SELECT generation, permission_mode FROM leaders WHERE party = ? AND session_id = ?"
        " ORDER BY generation DESC LIMIT 1",
        (ask_row["party"], session_id),
    ).fetchone()
    if leader is None:
        return None
    command = resume.resume_command(
        session_id,
        ask_row["party"],
        leader["generation"],
        leader["permission_mode"],
        party_commands.is_keeper(ctx.conn, ask_row["party"]),
    )
    if revive.find_transcript(paths.claude_projects_dir(), session_id) is None:
        return "{} (transcript not found)".format(command)
    return command


def _event_summary(kind, payload):
    if kind.startswith("task."):
        return "{}/{}".format(payload["quest"], payload["tid"])
    if kind.startswith("pr."):
        return "{}#{}".format(payload["repo"], payload["number"])
    if kind.startswith("ask."):
        return "#{}".format(payload["id"])
    if kind.startswith("quest."):
        return payload["slug"]
    if kind == "party.handed_off":
        return Path(payload["handoff_path"]).name
    return ""


def _recent_events(ctx, party):
    placeholders = ", ".join("?" for _ in _EVENT_KINDS)
    rows = ctx.conn.execute(
        "SELECT ts, kind, payload FROM events WHERE party = ? AND kind IN ({})"
        " ORDER BY seq DESC LIMIT ?".format(placeholders),
        (party, *_EVENT_KINDS, _EVENT_LIMIT),
    ).fetchall()
    return [
        {
            "ts": row["ts"],
            "time": timeutil.issued_label(row["ts"]),
            "kind": row["kind"],
            "summary": _event_summary(row["kind"], json.loads(row["payload"])),
        }
        for row in rows
    ]


def _optional_label(iso_text):
    if iso_text is None:
        return None
    return timeutil.issued_label(iso_text)


def build(ctx, ask_row):
    project, project_config = task_context.project_config(ctx, ask_row["party"])
    origin = _origin(ask_row)
    model = {
        "id": ask_row["id"],
        "party": ask_row["party"],
        "state": ask_row["state"],
        "question": ask_row["question"],
        "context": ask_row["context"],
        "options": json.loads(ask_row["options"]),
        "created_at": ask_row["created_at"],
        "created": timeutil.issued_label(ask_row["created_at"]),
        "answer": ask_row["answer"],
        "answered_at": ask_row["answered_at"],
        "answered": _optional_label(ask_row["answered_at"]),
        "refs": [
            _expand_ref(ctx, project, project_config, ref) for ref in json.loads(ask_row["refs"])
        ],
        "origin": origin,
        "resume": _resume(ctx, ask_row, origin),
        "events": _recent_events(ctx, ask_row["party"]),
    }
    return sanitize.sanitize_payload(model)


def _joined(parts):
    return "  ".join(part for part in parts if part)


def _task_lines(ref):
    if ref.get("missing"):
        return ["task    {}/{}  {}".format(ref["quest"], ref["tid"], _NOT_FOUND)]
    epic = None if ref["epic"] is None else "epic: {}".format(ref["epic"])
    lines = [
        _joined(
            [
                "task    {}/{}".format(ref["quest"], ref["tid"]),
                ref["title"],
                "[{}]".format(ref["state"]),
                epic,
            ]
        )
    ]
    if ref["spec"] is not None:
        lines.append("  spec:  {}".format(ref["spec"]))
    if ref["tasks"] is not None:
        lines.append("  tasks: {}".format(ref["tasks"]))
    return lines


def _card_lines(ref):
    if ref.get("missing"):
        return ["card    {}  {}".format(ref["key"], _NOT_FOUND)]
    return [_joined(["card    {}".format(ref["key"]), ref["status"], ref["url"]])]


def _pr_lines(ref):
    if ref.get("missing"):
        return [_joined(["pr      {}".format(ref["ref"][len("pr:"):]), _NOT_FOUND, ref["url"]])]
    checks = "checks: {} passing, {} failing, {} pending".format(
        ref["checks_passing"], ref["checks_failing"], ref["checks_pending"]
    )
    waits = None if not ref["waits"] else "waits: {}".format(ref["waits"])
    return [
        _joined(
            [
                "pr      {}".format(ref["ref"][len("pr:"):]),
                ref["url"],
                "lifecycle: {}".format(ref["lifecycle"]),
                checks,
                waits,
            ]
        )
    ]


_REF_LINES = {"task": _task_lines, "card": _card_lines, "pr": _pr_lines}


def _origin_lines(origin):
    if origin is None:
        return ["origin: not recorded"]
    session = origin["session_id"] or "unknown"
    if origin.get("session_name"):
        session = "{} ({})".format(session, origin["session_name"])
    in_progress = ", ".join(
        "{}/{} {}".format(task["quest"], task["tid"], task["title"]) for task in origin["in_progress"]
    )
    lines = [
        "origin (at creation)",
        "  session: {}".format(session),
        "  in progress: {}".format(in_progress or "none"),
        "  epics: {}   cards: {}".format(
            ", ".join(origin["epics"]) or "none", ", ".join(origin["cards"]) or "none"
        ),
    ]
    if origin.get("handoff_path"):
        lines.append("  handoff: {}".format(origin["handoff_path"]))
    return lines


def _closing_lines(model):
    if model["state"] == "open":
        return ['  → guild answer {} "..."'.format(model["id"])]
    if model["state"] != "answered":
        return []
    lines = ["  answer: {}".format(model["answer"])]
    if model["answered"] is not None:
        lines.append("  answered: {}".format(model["answered"]))
    return lines


def render_lines(model):
    lines = [
        "ask #{} · {} · {} · created {}".format(
            model["id"], model["party"], model["state"], model["created"]
        ),
        "  {}".format(model["question"]),
        "  context: {}".format(model["context"]),
    ]
    if model["options"]:
        lines.append("  options: {}".format(" | ".join(model["options"])))
    for ref in model["refs"]:
        lines.extend(_REF_LINES[ref["kind"]](ref))
    lines.extend(_origin_lines(model["origin"]))
    if model["resume"] is not None:
        lines.append("resume: {}".format(model["resume"]))
    lines.append("recent events ({}, last {})".format(model["party"], _EVENT_LIMIT))
    for event in model["events"]:
        lines.append(_joined(["  {}".format(event["time"]), event["kind"], event["summary"]]))
    lines.extend(_closing_lines(model))
    return lines
