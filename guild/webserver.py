import json
import sys
from http import server as http_server
from pathlib import Path
from urllib.parse import urlsplit

from guild import context, db, paths, timeutil
from guild.commands import board as board_commands

_WEB_DIR = Path(__file__).resolve().parent / "web"

_STATIC_FILES = {
    "/app.js": ("app.js", "application/javascript; charset=utf-8"),
    "/app.css": ("app.css", "text/css; charset=utf-8"),
}

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

    def _reject_host(self):
        self._write(421, b"host not allowed", "text/plain; charset=utf-8", None)

    def _not_found(self):
        self._write(404, b"not found", "text/plain; charset=utf-8", None)

    def _method_not_allowed(self):
        self._write(405, b"method not allowed", "text/plain; charset=utf-8", None)

    def _serve_file(self, name, content_type):
        body = (_WEB_DIR / name).read_bytes()
        self._write(200, body, content_type, None)

    def _serve_board(self):
        ctx = _board_context()
        try:
            payload = board_commands.board_model(ctx)
        finally:
            ctx.conn.close()
        body = json.dumps(payload).encode("utf-8")
        self._write(200, body, "application/json; charset=utf-8", "no-store")

    def _route_get(self):
        path = urlsplit(self.path).path
        if path == "/":
            return self._serve_file("index.html", "text/html; charset=utf-8")
        if path == "/api/board":
            return self._serve_board()
        if path in _STATIC_FILES:
            name, content_type = _STATIC_FILES[path]
            return self._serve_file(name, content_type)
        return self._not_found()

    def _dispatch(self, method):
        if not self._host_allowed():
            return self._reject_host()
        if method != "GET":
            return self._method_not_allowed()
        return self._route_get()

    def do_GET(self):
        self._dispatch("GET")

    def do_HEAD(self):
        self._dispatch("HEAD")

    def do_POST(self):
        self._dispatch("POST")

    def do_PUT(self):
        self._dispatch("PUT")

    def do_PATCH(self):
        self._dispatch("PATCH")

    def do_DELETE(self):
        self._dispatch("DELETE")


def start(port):
    server = http_server.ThreadingHTTPServer(("127.0.0.1", port), BoardRequestHandler)
    server.daemon_threads = True
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
