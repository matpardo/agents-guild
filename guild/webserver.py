import hmac
import json
import re
import secrets
import sys
from http import server as http_server
from pathlib import Path
from urllib.parse import urlsplit

from guild import context, db, origin, paths, timeutil
from guild.commands import ask as ask_commands
from guild.commands import board as board_commands
from guild.errors import GuildError

_WEB_DIR = Path(__file__).resolve().parent / "web"

_STATIC_FILES = {
    "/app.js": ("app.js", "application/javascript; charset=utf-8"),
    "/app.css": ("app.css", "text/css; charset=utf-8"),
}

_MAX_BODY_BYTES = 16384
_ASK_ACTION_RE = re.compile(r"^/api/asks/([^/]+)/(answer|dismiss)$")
_ASK_ID_RE = re.compile(r"^[1-9][0-9]{0,17}$")
_JSON_CONTENT_TYPE = "application/json; charset=utf-8"

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
        conn, None, None, timeutil.utcnow(), None,
        paths.claude_sessions_dir(), paths.projects_config_dir(), None,
    )


def _action_context():
    conn = db.connect(paths.db_path())
    return context.RunContext(
        conn, None, Path.cwd(), timeutil.utcnow(), origin.current_origin(),
        paths.claude_sessions_dir(), paths.projects_config_dir(), paths.state_dir(),
    )


def _run_ask_action(action, ask_id, payload):
    ctx = _action_context()
    try:
        if action == "answer":
            return ask_commands.answer(ctx, ask_id, payload["answer"])
        return ask_commands.dismiss(ctx, ask_id)
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
        self.end_headers()
        self.wfile.write(body)

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

    def _body_length(self):
        raw = self.headers.get("Content-Length")
        if raw is None:
            raise _RequestRejected(411, "content length required")
        if not raw.isascii() or not raw.isdigit():
            raise _RequestRejected(400, "invalid content length")
        length = int(raw)
        if length > _MAX_BODY_BYTES:
            raise _RequestRejected(413, "request body too large")
        return length

    def _read_json_object(self):
        raw = self.rfile.read(self._body_length())
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise _RequestRejected(400, "body must be valid JSON")
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

    def _read_action_payload(self, action):
        payload = self._read_json_object()
        if action == "answer" and not isinstance(payload.get("answer"), str):
            raise _RequestRejected(400, "answer must be a string")
        return payload

    def _post_action(self, action, run):
        try:
            self._check_write_headers()
            payload = self._read_action_payload(action)
        except _RequestRejected as rejected:
            return self._write_json(rejected.status, {"error": rejected.message})
        try:
            message = run(payload)
        except GuildError as error:
            return self._write_json(422, {"error": error.message})
        return self._write_json(200, {"ok": True, "message": message})

    def _route_post(self):
        path = urlsplit(self.path).path
        ask_match = _ASK_ACTION_RE.match(path)
        if ask_match is not None:
            ask_id, action = ask_match.groups()
            if not _ASK_ID_RE.match(ask_id):
                return self._not_found()
            return self._post_action(action, lambda payload: _run_ask_action(action, int(ask_id), payload))
        return self._method_not_allowed()

    def _serve_session(self):
        self._write_json(200, {"token": self.server.session_token})

    def _reject_host(self):
        self._write(421, b"host not allowed", "text/plain; charset=utf-8", None)

    def _not_found(self):
        self._write(404, b"not found", "text/plain; charset=utf-8", None)

    def _method_not_allowed(self):
        self._write(405, b"method not allowed", "text/plain; charset=utf-8", None)

    def _serve_file(self, name, content_type):
        body = (_WEB_DIR / name).read_bytes()
        self._write(200, body, content_type, None)

    def _serve_model(self, build_model):
        ctx = _board_context()
        try:
            payload = build_model(ctx)
        finally:
            ctx.conn.close()
        body = json.dumps(payload).encode("utf-8")
        self._write(200, body, "application/json; charset=utf-8", "no-store")

    def _route_get(self):
        path = urlsplit(self.path).path
        if path == "/":
            return self._serve_file("index.html", "text/html; charset=utf-8")
        if path == "/api/board":
            return self._serve_model(board_commands.board_model)
        if path == "/api/session":
            return self._serve_session()
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


def start(port):
    server = http_server.ThreadingHTTPServer(("127.0.0.1", port), BoardRequestHandler)
    server.daemon_threads = True
    server.session_token = secrets.token_urlsafe(32)
    return server


def serve_forever(port):
    server = start(port)
    actual_port = server.server_address[1]
    print("guild web: http://127.0.0.1:{}/".format(actual_port), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
