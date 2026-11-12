import hmac
import json
import os
import re
import secrets
import sqlite3
import sys
import threading
from http import server as http_server
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from guild import ask_detail, context, db, due_jobs, origin, paths, timeutil, tmux_windows
from guild.commands import adventurer as adventurer_commands
from guild.commands import ask as ask_commands
from guild.commands import base_pause as base_pause_commands
from guild.commands import board as board_commands
from guild.commands import compact as compact_commands
from guild.commands import handoff as handoff_commands
from guild.commands import history as history_commands
from guild.commands import idea as idea_commands
from guild.commands import memory as memory_commands
from guild.commands import notice as notice_commands
from guild.commands import party as party_commands
from guild.commands import pr as pr_commands
from guild.commands import quest as quest_commands
from guild.commands import raid_pause as raid_pause_commands
from guild.commands import realm as realm_commands
from guild.commands import resources as resources_commands
from guild.commands import revive as revive_commands
from guild.commands import task as task_commands
from guild.errors import GuildError
from guild.realm import hub as realm_hub
from guild.resources import report as resources_report

_DUE_JOBS_TICK_SECONDS = 60
_WEB_DIR = Path(__file__).resolve().parent / "web"

_STATIC_FILES = {
    "/app.js": ("app.js", "application/javascript; charset=utf-8"),
    "/app.css": ("app.css", "text/css; charset=utf-8"),
    "/history.js": ("history.js", "application/javascript; charset=utf-8"),
    "/progress.js": ("progress.js", "application/javascript; charset=utf-8"),
}

_PAGE_FILES = ("index.html", "history.html", "progress.html")

_MAX_BODY_BYTES = 16384
_PASTED_FILE_ACTIONS = ("import-idea", "confirm-export-idea")
_INTERNAL_ERROR = {"error": "internal error"}
_ASK_ACTION_RE = re.compile(r"^/api/asks/([^/]+)/(answer|dismiss)$")
_NOTICE_ACTION_RE = re.compile(r"^/api/notices/([^/]+)/(seen|unseen)$")
_PR_ACTION_RE = re.compile(r"^/api/prs/([^/]+/[^/]+)/(\d+)/(block|unblock|relink|untrack|ack)$")
_BASE_ACTION_RE = re.compile(r"^/api/bases/([^/]+/[^/]+)/(pause|resume)$")
_RAID_ACTION_RE = re.compile(r"^/api/raids/([^/]+)/(pause|resume)$")
_MEMORY_ACTION_RE = re.compile(r"^/api/memory/([^/]+)/([1-9][0-9]*)/rm$")
_TASK_MOVE_RE = re.compile(r"^/api/quests/([^/]+)/tasks/([^/]+)/move$")
_TASK_DISCARD_RE = re.compile(r"^/api/quests/([^/]+)/tasks/([^/]+)/(discard|restore)$")
_PARTY_HANDOFF_RE = re.compile(r"^/api/parties/([^/]+)/hand-off$")
_PARTY_REVIVE_RE = re.compile(r"^/api/parties/([^/]+)/revive$")
_PARTY_GOAL_RE = re.compile(r"^/api/parties/([^/]+)/goal$")
_PARTY_PARK_RE = re.compile(r"^/api/parties/([^/]+)/(park|unpark)$")
_IDEA_ACTION_RE = re.compile(r"^/api/ideas/([^/]+)/(edit|delete|link|unlink|unexport)$")
_IDEA_CREATE_PATH = "/api/ideas/create"
_IDEA_EXPORT_PATH = "/api/ideas/export"
_IDEA_EXPORT_PROJECT_PATH = "/api/ideas/export-project"
_IDEA_IMPORT_PATH = "/api/ideas/import"
_IDEA_CONFIRM_EXPORT_PATH = "/api/ideas/confirm-export"
_QUEST_ACTION_RE = re.compile(r"^/api/quests/([^/]+)/(take|release)$")
_QUEST_CREATE_PATH = "/api/quests/create-open"
_ADVENTURER_DISMISS_RE = re.compile(r"^/api/adventurers/([^/]+)/dismiss$")
_ADVENTURER_REVIVE_RE = re.compile(r"^/api/adventurers/([^/]+)/revive$")
_REVIVE_ALL_PATH = "/api/revive"
_COMPACT_PATH = "/api/compact"
_RESOURCES_COLLECT_PATH = "/api/resources/collect"
_REALM_REFRESH_PATH = "/api/realm/refresh"
_REALM_DOCTOR_PATH = "/api/realm/doctor"
_REALM_INBOX_REFRESH_PATH = "/api/realm/inbox/refresh"
_REALM_INBOX_ACTION_RE = re.compile(r"^/api/realm/inbox/([^/]+)/(fetch|drop)$")
_SEEN_ALL_PATH = "/api/notices/seen-all"
_NOTICE_CREATE_PATH = "/api/notices/create"
_ANSWERED_ASKS_PATH = "/api/asks/answered"
_ASK_DETAIL_RE = re.compile(r"^/api/asks/(\d+)$")
_API_GET_PATHS = ("/api/board", _ANSWERED_ASKS_PATH, "/api/history", "/api/resources")
_ASK_ID_RE = re.compile(r"^[1-9][0-9]{0,17}$")
_JSON_CONTENT_TYPE = "application/json; charset=utf-8"
_RESOURCES_SINCE = "1d"

_SECURITY_HEADERS = (
    (
        "Content-Security-Policy",
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; "
        "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
    ),
    ("X-Content-Type-Options", "nosniff"),
    ("Referrer-Policy", "no-referrer"),
)


def _board_context():
    conn = db.connect(paths.db_path())
    return context.RunContext(
        conn,
        None,
        None,
        timeutil.utcnow(),
        None,
        paths.claude_sessions_dir(),
        paths.projects_config_dir(),
        paths.state_dir(),
    )


def _action_context():
    conn = db.connect(paths.db_path())
    return context.RunContext(
        conn,
        None,
        Path.cwd(),
        timeutil.utcnow(),
        origin.current_origin(),
        paths.claude_sessions_dir(),
        paths.projects_config_dir(),
        paths.state_dir(),
    )


def _history_model(query):
    params = parse_qs(query)

    def build(ctx):
        return history_commands.build_model(
            ctx.conn,
            ctx.now,
            _first_param(params, "party"),
            _first_param(params, "raid"),
            _first_param(params, "project"),
            ctx.projects_dir,
        )

    return build


def _resources_model(query):
    params = parse_qs(query)
    since = _first_param(params, "since") or _RESOURCES_SINCE

    def build(ctx):
        return resources_report.build_model(ctx.conn, ctx.now, _first_param(params, "project"), since, ctx.projects_dir)

    return build


def _answered_asks_model(query):
    page_text = _first_param(parse_qs(query), "page")

    def build(ctx):
        if page_text is None:
            return board_commands.answered_asks_model(ctx.conn, 1)
        if not page_text.isdigit():
            raise GuildError("page must be a positive integer", 1)
        return board_commands.answered_asks_model(ctx.conn, int(page_text))

    return build


def _first_param(params, name):
    values = params.get(name)
    if not values:
        return None
    return values[0]


def _run_ask_action(action, ask_id, payload):
    ctx = _action_context()
    try:
        if action == "answer":
            return ask_commands.answer(ctx, ask_id, payload["answer"])
        return ask_commands.dismiss(ctx, ask_id)
    finally:
        ctx.conn.close()


def _run_notice_action(action, notice_id):
    ctx = _action_context()
    try:
        if action == "seen":
            return notice_commands.mark_seen(ctx, notice_id)
        return notice_commands.mark_unseen(ctx, notice_id)
    finally:
        ctx.conn.close()


def _run_seen_all():
    ctx = _action_context()
    try:
        return notice_commands.mark_all_seen(ctx)
    finally:
        ctx.conn.close()


def _run_notice_create(payload):
    ctx = _action_context()
    try:
        return notice_commands.create(ctx, payload["text"], payload["to"], payload["ttl"], None)
    finally:
        ctx.conn.close()


_IDEA_TEXT_KEYS = ("title", "description", "requester", "deadline", "project")


def _run_idea_create(payload):
    ctx = _action_context()
    try:
        return idea_commands.add(
            ctx,
            payload["title"],
            payload["description"],
            payload.get("requester"),
            payload.get("deadline"),
            payload.get("project"),
        )
    finally:
        ctx.conn.close()


def _idea_export_file(prefix):
    directory = paths.ensure_private_dir(paths.idea_exports_dir())
    return str(directory / "{}-{}.md".format(prefix, secrets.token_hex(4)))


def _run_idea_export(payload):
    ctx = _action_context()
    try:
        return idea_commands.export_ids(ctx, payload["ids"], payload["destination"], _idea_export_file("ideas"))
    finally:
        ctx.conn.close()


def _run_idea_export_project(payload):
    ctx = _action_context()
    try:
        return idea_commands.export_project(ctx, payload["project"], payload["destination"], _idea_export_file("ideas"))
    finally:
        ctx.conn.close()


def _run_idea_import(payload):
    ctx = _action_context()
    try:
        return idea_commands.import_text(ctx, payload["text"], _idea_export_file("receipt"), payload.get("project"))
    finally:
        ctx.conn.close()


def _run_idea_confirm_export(payload):
    ctx = _action_context()
    try:
        return idea_commands.confirm_export_text(ctx, payload["text"])
    finally:
        ctx.conn.close()


def _run_idea_action(action, idea_id, payload):
    ctx = _action_context()
    try:
        if action == "delete":
            return idea_commands.delete(ctx, idea_id)
        if action == "unexport":
            return idea_commands.unexport(ctx, idea_id)
        if action == "link" and "adventurer" in payload:
            return idea_commands.link_for_adventurer(ctx, idea_id, payload["adventurer"])
        if action == "unlink" and "adventurer" in payload:
            return idea_commands.unlink_for_adventurer(ctx, idea_id, payload["adventurer"])
        if action == "link":
            return idea_commands.link_for_party(ctx, idea_id, payload["party"])
        if action == "unlink":
            return idea_commands.unlink_for_party(ctx, idea_id, payload["party"])
        fields = {key: payload[key] for key in _IDEA_TEXT_KEYS if key in payload}
        return idea_commands.edit(ctx, idea_id, fields)
    finally:
        ctx.conn.close()


def _run_quest_create(payload):
    ctx = _action_context()
    try:
        return quest_commands.add_open(
            ctx, payload["project"], payload["slug"], payload["title"], payload["epic"], payload["tasks"]
        )
    finally:
        ctx.conn.close()


def _run_quest_action(action, slug, payload):
    ctx = _action_context()
    try:
        if action == "take":
            return quest_commands.take_for_party(ctx, slug, payload["party"])
        return quest_commands.release_for_owner(ctx, slug)
    finally:
        ctx.conn.close()


def _run_adventurer_dismiss(adventurer_id):
    ctx = _action_context()
    try:
        return adventurer_commands.dismiss(ctx, adventurer_id)
    finally:
        ctx.conn.close()


def _run_revive(party_names, adventurer_ids, select_all):
    ctx = _action_context()
    try:
        return revive_commands.run(
            ctx, party_names, adventurer_ids, select_all, False, paths.claude_projects_dir(), tmux_windows.Tmux(), None
        )
    finally:
        ctx.conn.close()


def _run_base_action(action, repo):
    ctx = _action_context()
    try:
        if action == "pause":
            return base_pause_commands.pause(ctx, repo)
        return base_pause_commands.resume(ctx, repo)
    finally:
        ctx.conn.close()


def _run_raid_action(action, raid_name):
    ctx = _action_context()
    try:
        if action == "pause":
            return raid_pause_commands.pause(ctx, raid_name)
        return raid_pause_commands.resume(ctx, raid_name)
    finally:
        ctx.conn.close()


def _run_memory_action(party, seq):
    ctx = _action_context()
    try:
        return memory_commands.rm(ctx, "{}/{}".format(party, seq))
    finally:
        ctx.conn.close()


def _run_party_handoff_action(party):
    ctx = _action_context()
    try:
        return handoff_commands.run_for_party(ctx, party)
    finally:
        ctx.conn.close()


def _run_party_goal_action(party, payload):
    ctx = _action_context()
    try:
        return party_commands.set_goal(ctx, party, payload.get("goal"), payload.get("done_when"))
    finally:
        ctx.conn.close()


def _run_party_park_action(action, party, payload):
    ctx = _action_context()
    try:
        if action == "park":
            return party_commands.park(ctx, party, payload["reason"])
        return party_commands.unpark(ctx, party)
    finally:
        ctx.conn.close()


def _run_compact():
    ctx = _action_context()
    try:
        return compact_commands.run(ctx, False)
    finally:
        ctx.conn.close()


def _run_resources_collect():
    ctx = _action_context()
    try:
        return resources_commands.run_collect(ctx)
    finally:
        ctx.conn.close()


def _run_realm_refresh():
    ctx = _action_context()
    try:
        return realm_commands.realm_status_model(ctx)
    finally:
        ctx.conn.close()


def _run_realm_doctor():
    ctx = _action_context()
    try:
        lines = realm_commands.doctor_lines(ctx)
    finally:
        ctx.conn.close()
    return {
        "ok": all(passed for passed, _ in lines),
        "lines": [{"passed": passed, "text": text} for passed, text in lines],
    }


def _run_realm_inbox_refresh():
    ctx = _action_context()
    try:
        return realm_commands.inbox_model(ctx, None)
    finally:
        ctx.conn.close()


def _run_realm_inbox_action(action, file_id):
    if action == "fetch":
        return realm_commands.fetch(file_id, str(paths.realm_files_dir()), None)
    return {"message": realm_commands.drop(file_id, None)}


def _run_task_move_action(quest, tid, payload):
    ctx = _action_context()
    try:
        return task_commands.move_for_owner(ctx, quest, tid, payload["to"])
    finally:
        ctx.conn.close()


def _run_task_discard_action(action, quest, tid, payload):
    ctx = _action_context()
    try:
        if action == "discard":
            return task_commands.discard_for_owner(ctx, quest, tid, payload["reason"], payload["force"])
        return task_commands.restore_for_owner(ctx, quest, tid)
    finally:
        ctx.conn.close()


def _run_pr_action(action, ref, payload):
    ctx = _action_context()
    try:
        if action == "block":
            return pr_commands.block_external(ctx, ref, payload["reason"])
        if action == "relink":
            return pr_commands.relink_as_human(ctx, ref, payload.get("task"), payload.get("card"))
        if action == "untrack":
            return pr_commands.untrack_as_human(ctx, ref)
        if action == "ack":
            return pr_commands.ack_comments(ctx, ref)
        return pr_commands.unblock_external(ctx, ref)
    finally:
        ctx.conn.close()


class _RequestRejected(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


class BoardRequestHandler(http_server.BaseHTTPRequestHandler):
    server_version = "guild-web/1"

    def log_message(self, format_string, *args):
        return

    def log_error(self, format_string, *args):
        sys.stderr.write("guild web: {}\n".format(format_string % args))

    def _host_allowed(self):
        port = self.server.server_address[1]
        allowed = ("127.0.0.1:{}".format(port), "localhost:{}".format(port))
        return self.headers.get("Host") in allowed

    def _write(self, status, body, content_type, cache_control):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if cache_control is not None:
            self.send_header("Cache-Control", cache_control)
        for name, value in _SECURITY_HEADERS:
            self.send_header(name, value)
        try:
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            return

    def _write_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self._write(status, body, _JSON_CONTENT_TYPE, "no-store")

    def _origin_allowed(self):
        port = self.server.server_address[1]
        allowed = ("http://127.0.0.1:{}".format(port), "http://localhost:{}".format(port))
        return self.headers.get("Origin") in allowed

    def _token_valid(self):
        supplied = self.headers.get("X-Guild-Token")
        if supplied is None:
            return False
        expected = self.server.session_token.encode("utf-8")
        return hmac.compare_digest(supplied.encode("utf-8"), expected)

    def _content_type_is_json(self):
        header = self.headers.get("Content-Type")
        if header is None:
            return False
        return header.split(";")[0].strip().lower() == "application/json"

    def _body_length(self, limit):
        raw = self.headers.get("Content-Length")
        if raw is None:
            raise _RequestRejected(411, "content length required")
        if not raw.isascii() or not raw.isdigit():
            raise _RequestRejected(400, "invalid content length")
        length = int(raw)
        if length > limit:
            raise _RequestRejected(413, "request body too large")
        return length

    def _read_json_object(self, limit):
        raw = self.rfile.read(self._body_length(limit))
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError, RecursionError):
            raise _RequestRejected(400, "body must be valid JSON") from None
        if not isinstance(payload, dict):
            raise _RequestRejected(400, "body must be a JSON object")
        return payload

    def _check_write_headers(self):
        if not self._origin_allowed():
            raise _RequestRejected(403, "origin not allowed")
        if not self._token_valid():
            raise _RequestRejected(403, "invalid session token")
        if not self._content_type_is_json():
            raise _RequestRejected(415, "content type must be application/json")

    def _check_idea_payload(self, action, payload):
        required = ("title", "description") if action == "create-idea" else ()
        for key in required:
            if not isinstance(payload.get(key), str):
                raise _RequestRejected(400, "{} must be a string".format(key))
        for key in _IDEA_TEXT_KEYS:
            if key in payload and not isinstance(payload[key], str) and payload[key] is not None:
                raise _RequestRejected(400, "{} must be a string or null".format(key))

    def _check_idea_transfer_payload(self, action, payload):
        if action == "export-idea":
            ids = payload.get("ids")
            if not isinstance(ids, list) or not all(isinstance(i, int) and not isinstance(i, bool) for i in ids):
                raise _RequestRejected(400, "ids must be a list of integers")
        required = {
            "export-idea": ("destination",),
            "export-project-idea": ("project", "destination"),
            "import-idea": ("text",),
            "confirm-export-idea": ("text",),
        }[action]
        for key in required:
            if not isinstance(payload.get(key), str):
                raise _RequestRejected(400, "{} must be a string".format(key))
        if action == "import-idea" and payload.get("project") is not None and not isinstance(payload["project"], str):
            raise _RequestRejected(400, "project must be a string or null")

    def _check_idea_holder(self, payload):
        if ("party" in payload) == ("adventurer" in payload):
            raise _RequestRejected(400, "pass exactly one of party or adventurer")
        if "party" in payload and not isinstance(payload["party"], str):
            raise _RequestRejected(400, "party must be a string")
        adventurer = payload.get("adventurer")
        if "adventurer" in payload and (not isinstance(adventurer, int) or isinstance(adventurer, bool)):
            raise _RequestRejected(400, "adventurer must be an integer")

    def _check_quest_payload(self, payload):
        for key in ("project", "slug", "title", "epic"):
            if not isinstance(payload.get(key), str):
                raise _RequestRejected(400, "{} must be a string".format(key))
        tasks = payload.get("tasks")
        if not isinstance(tasks, list) or not all(isinstance(tid, str) for tid in tasks):
            raise _RequestRejected(400, "tasks must be a list of strings")

    def _read_action_payload(self, action):
        limit = realm_hub.INBOX_MAX_BODY if action in _PASTED_FILE_ACTIONS else _MAX_BODY_BYTES
        payload = self._read_json_object(limit)
        if action == "answer" and not isinstance(payload.get("answer"), str):
            raise _RequestRejected(400, "answer must be a string")
        if action == "create" and not all(isinstance(payload.get(key), str) for key in ("text", "to", "ttl")):
            raise _RequestRejected(400, "text, to and ttl must be strings")
        if action in ("create-idea", "edit-idea"):
            self._check_idea_payload(action, payload)
        if action in ("export-idea", "export-project-idea", "import-idea", "confirm-export-idea"):
            self._check_idea_transfer_payload(action, payload)
        if action == "create-quest":
            self._check_quest_payload(payload)
        if action in ("link-idea", "unlink-idea"):
            self._check_idea_holder(payload)
        if action == "take-quest" and not isinstance(payload.get("party"), str):
            raise _RequestRejected(400, "party must be a string")
        if action == "move" and not isinstance(payload.get("to"), str):
            raise _RequestRejected(400, "to must be a string")
        if action == "discard" and not (
            isinstance(payload.get("reason"), str) and isinstance(payload.get("force"), bool)
        ):
            raise _RequestRejected(400, "reason must be a string and force a boolean")
        if action in ("block", "park") and not isinstance(payload.get("reason"), str):
            raise _RequestRejected(400, "reason must be a string")
        if action == "set-goal" and not all(isinstance(payload.get(key, ""), str) for key in ("goal", "done_when")):
            raise _RequestRejected(400, "goal and done_when must be strings")
        if action == "relink" and not all(isinstance(payload.get(key, ""), str) for key in ("task", "card")):
            raise _RequestRejected(400, "task and card must be strings")
        return payload

    def _post_action(self, action, run):
        return self._post_payload(action, lambda payload: {"ok": True, "message": run(payload)})

    def _post_payload(self, action, build):
        try:
            self._check_write_headers()
            payload = self._read_action_payload(action)
        except _RequestRejected as rejected:
            return self._write_json(rejected.status, {"error": rejected.message})
        try:
            body = build(payload)
        except GuildError as error:
            return self._write_json(422, {"error": error.message})
        except sqlite3.Error as error:
            return self._write_json(500, {"error": str(error)})
        except Exception:
            return self._write_json(500, _INTERNAL_ERROR)
        return self._write_json(200, body)

    def _route_post(self):
        path = urlsplit(self.path).path
        ask_match = _ASK_ACTION_RE.match(path)
        if ask_match is not None:
            ask_id, action = ask_match.groups()
            if not _ASK_ID_RE.match(ask_id):
                return self._not_found()
            return self._post_action(action, lambda payload: _run_ask_action(action, int(ask_id), payload))
        pr_match = _PR_ACTION_RE.match(path)
        if pr_match is not None:
            repo, number, action = pr_match.groups()
            ref = "{}#{}".format(repo, number)
            return self._post_action(action, lambda payload: _run_pr_action(action, ref, payload))
        base_match = _BASE_ACTION_RE.match(path)
        if base_match is not None:
            repo, action = base_match.groups()
            return self._post_action(action, lambda payload: _run_base_action(action, repo))
        raid_match = _RAID_ACTION_RE.match(path)
        if raid_match is not None:
            raid_name, action = raid_match.groups()
            return self._post_action(action, lambda payload: _run_raid_action(action, raid_name))
        if path == _NOTICE_CREATE_PATH:
            return self._post_action("create", _run_notice_create)
        if path == _IDEA_CREATE_PATH:
            return self._post_action("create-idea", _run_idea_create)
        if path == _IDEA_EXPORT_PATH:
            return self._post_action("export-idea", _run_idea_export)
        if path == _IDEA_EXPORT_PROJECT_PATH:
            return self._post_action("export-project-idea", _run_idea_export_project)
        if path == _IDEA_IMPORT_PATH:
            return self._post_action("import-idea", _run_idea_import)
        if path == _IDEA_CONFIRM_EXPORT_PATH:
            return self._post_action("confirm-export-idea", _run_idea_confirm_export)
        idea_match = _IDEA_ACTION_RE.match(path)
        if idea_match is not None:
            idea_id, action = idea_match.groups()
            if not _ASK_ID_RE.match(idea_id):
                return self._not_found()
            post_action = action + "-idea"
            return self._post_action(post_action, lambda payload: _run_idea_action(action, int(idea_id), payload))
        if path == _QUEST_CREATE_PATH:
            return self._post_action("create-quest", _run_quest_create)
        quest_match = _QUEST_ACTION_RE.match(path)
        if quest_match is not None:
            slug, action = quest_match.groups()
            return self._post_action(action + "-quest", lambda payload: _run_quest_action(action, slug, payload))
        adventurer_match = _ADVENTURER_DISMISS_RE.match(path)
        if adventurer_match is not None:
            adventurer_id = adventurer_match.group(1)
            if not _ASK_ID_RE.match(adventurer_id):
                return self._not_found()
            return self._post_action("dismiss-adventurer", lambda payload: _run_adventurer_dismiss(int(adventurer_id)))
        if path == _REVIVE_ALL_PATH:
            return self._post_action("revive-all", lambda payload: _run_revive([], [], True))
        adventurer_revive_match = _ADVENTURER_REVIVE_RE.match(path)
        if adventurer_revive_match is not None:
            adventurer_id = adventurer_revive_match.group(1)
            if not _ASK_ID_RE.match(adventurer_id):
                return self._not_found()
            return self._post_action("revive-adventurer", lambda payload: _run_revive([], [int(adventurer_id)], False))
        party_revive_match = _PARTY_REVIVE_RE.match(path)
        if party_revive_match is not None:
            party = party_revive_match.group(1)
            return self._post_action("revive-party", lambda payload: _run_revive([party], [], False))
        if path == _COMPACT_PATH:
            return self._post_action("compact", lambda payload: _run_compact())
        if path == _RESOURCES_COLLECT_PATH:
            return self._post_action("resources-collect", lambda payload: _run_resources_collect())
        if path == _REALM_REFRESH_PATH:
            return self._post_payload("realm-refresh", lambda payload: dict(_run_realm_refresh(), ok=True))
        if path == _REALM_DOCTOR_PATH:
            return self._post_payload("realm-doctor", lambda payload: _run_realm_doctor())
        if path == _REALM_INBOX_REFRESH_PATH:
            return self._post_payload("realm-inbox-refresh", lambda payload: dict(_run_realm_inbox_refresh(), ok=True))
        realm_inbox_match = _REALM_INBOX_ACTION_RE.match(path)
        if realm_inbox_match is not None:
            file_id, action = realm_inbox_match.groups()
            if not realm_hub.is_file_id(file_id):
                return self._not_found()
            return self._post_payload(
                "realm-inbox-" + action, lambda payload: dict(_run_realm_inbox_action(action, file_id), ok=True)
            )
        if path == _SEEN_ALL_PATH:
            return self._post_action("seen-all", lambda payload: _run_seen_all())
        memory_match = _MEMORY_ACTION_RE.match(path)
        if memory_match is not None:
            party, seq = memory_match.groups()
            return self._post_action("rm", lambda payload: _run_memory_action(party, seq))
        party_handoff_match = _PARTY_HANDOFF_RE.match(path)
        if party_handoff_match is not None:
            party = party_handoff_match.group(1)
            return self._post_action("hand-off", lambda payload: _run_party_handoff_action(party))
        party_goal_match = _PARTY_GOAL_RE.match(path)
        if party_goal_match is not None:
            party = party_goal_match.group(1)
            return self._post_action("set-goal", lambda payload: _run_party_goal_action(party, payload))
        party_park_match = _PARTY_PARK_RE.match(path)
        if party_park_match is not None:
            party, action = party_park_match.groups()
            return self._post_action(action, lambda payload: _run_party_park_action(action, party, payload))
        task_move_match = _TASK_MOVE_RE.match(path)
        if task_move_match is not None:
            quest, tid = task_move_match.groups()
            return self._post_action("move", lambda payload: _run_task_move_action(quest, tid, payload))
        task_discard_match = _TASK_DISCARD_RE.match(path)
        if task_discard_match is not None:
            quest, tid, action = task_discard_match.groups()
            return self._post_action(action, lambda payload: _run_task_discard_action(action, quest, tid, payload))
        notice_match = _NOTICE_ACTION_RE.match(path)
        if notice_match is None:
            return self._method_not_allowed()
        notice_id, action = notice_match.groups()
        if not _ASK_ID_RE.match(notice_id):
            return self._not_found()
        return self._post_action(action, lambda payload: _run_notice_action(action, int(notice_id)))

    def _reject_host(self):
        self._write(421, b"host not allowed", "text/plain; charset=utf-8", None)

    def _not_found(self):
        self._write(404, b"not found", "text/plain; charset=utf-8", None)

    def _method_not_allowed(self):
        self._write(405, b"method not allowed", "text/plain; charset=utf-8", None)

    def _serve_file(self, name, content_type):
        self._write(200, self.server.static_bodies[name], content_type, None)

    def _serve_model(self, build_model):
        ctx = _board_context()
        try:
            payload = build_model(ctx)
        except GuildError as error:
            return self._write_json(422, {"error": error.message})
        except Exception:
            return self._write_json(500, _INTERNAL_ERROR)
        finally:
            ctx.conn.close()
        body = json.dumps(payload).encode("utf-8")
        self._write(200, body, "application/json; charset=utf-8", "no-store")

    def _serve_ask_detail(self, ask_id):
        ctx = _board_context()
        try:
            row = ctx.conn.execute("SELECT * FROM asks WHERE id = ?", (ask_id,)).fetchone()
            if row is None:
                return self._write_json(404, {"error": "unknown ask #{}".format(ask_id)})
            return self._write_json(200, ask_detail.build(ctx, row))
        finally:
            ctx.conn.close()

    def _route_get(self):
        parts = urlsplit(self.path)
        path = parts.path
        if path == "/":
            return self._serve_file("index.html", "text/html; charset=utf-8")
        ask_match = _ASK_DETAIL_RE.match(path)
        if (path in _API_GET_PATHS or ask_match is not None) and not self._token_valid():
            return self._write_json(403, {"error": "invalid session token"})
        if path == "/api/board":
            return self._serve_model(board_commands.board_model)
        if path == _ANSWERED_ASKS_PATH:
            return self._serve_model(_answered_asks_model(parts.query))
        if ask_match is not None:
            return self._serve_ask_detail(int(ask_match.group(1)))
        if path == "/history":
            return self._serve_file("history.html", "text/html; charset=utf-8")
        if path == "/progress":
            return self._serve_file("progress.html", "text/html; charset=utf-8")
        if path == "/api/history":
            return self._serve_model(_history_model(parts.query))
        if path == "/api/resources":
            return self._serve_model(_resources_model(parts.query))
        if path in _STATIC_FILES:
            name, content_type = _STATIC_FILES[path]
            return self._serve_file(name, content_type)
        return self._not_found()

    def _dispatch(self, method):
        if not self._host_allowed():
            return self._reject_host()
        if method == "POST":
            return self._route_post()
        if method != "GET":
            return self._method_not_allowed()
        return self._route_get()

    def do_GET(self):
        self._dispatch("GET")

    def do_HEAD(self):
        self._dispatch("HEAD")

    def do_POST(self):
        self._dispatch("POST")

    def do_OPTIONS(self):
        self._dispatch("OPTIONS")

    def do_PUT(self):
        self._dispatch("PUT")

    def do_PATCH(self):
        self._dispatch("PATCH")

    def do_DELETE(self):
        self._dispatch("DELETE")


_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{43}")


def _load_or_create_session_token(state_dir):
    token_path = state_dir / "web-token"
    if token_path.is_file() and not token_path.is_symlink():
        token = token_path.read_text().removesuffix("\n")
        if _TOKEN_PATTERN.fullmatch(token):
            token_path.chmod(0o600)
            return token
    token = secrets.token_urlsafe(32)
    state_dir.mkdir(parents=True, exist_ok=True)
    token_path.unlink(missing_ok=True)
    descriptor = os.open(str(token_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        handle.write(token + "\n")
    return token


def start(port, state_dir):
    server = http_server.ThreadingHTTPServer(("127.0.0.1", port), BoardRequestHandler)
    server.daemon_threads = True
    server.session_token = _load_or_create_session_token(state_dir)
    names = _PAGE_FILES + tuple(name for name, _ in _STATIC_FILES.values())
    server.static_bodies = {name: (_WEB_DIR / name).read_bytes() for name in names}
    return server


def _start_due_jobs_ticker(state_dir):
    stop_event = threading.Event()
    thread = threading.Thread(
        target=due_jobs.tick_until_stopped,
        args=(stop_event, _DUE_JOBS_TICK_SECONDS, state_dir, Path.home(), due_jobs.spawn_detached),
        daemon=True,
    )
    thread.start()
    return stop_event, thread


def serve_forever(port, state_dir):
    server = start(port, state_dir)
    ticker_stop, ticker_thread = _start_due_jobs_ticker(state_dir)
    actual_port = server.server_address[1]
    print("guild web: http://127.0.0.1:{}/#t={}".format(actual_port, server.session_token), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        ticker_stop.set()
        ticker_thread.join()
        server.server_close()
    return 0
