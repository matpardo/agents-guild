import hashlib
import hmac
import json
import re
import secrets
import socket
import ssl
import sys
import threading
from http import server as http_server

from guild import paths, timeutil
from guild.errors import GuildError
from guild.realm import hubconfig, status

STATUS_MAX_BODY = 16384
INBOX_MAX_BODY = 400 * 1024
_OVERSIZE_DRAIN_BYTES = 1024 * 1024
CONTENT_MAX_BYTES = 256 * 1024
INBOX_MAX_FILES = 100
INBOX_MAX_PER_SENDER = 20
MAX_CONNECTIONS = 32
_REQUEST_TIMEOUT_SECONDS = 30
PRE_AUTH_DEADLINE_SECONDS = 10
_ID_RE = re.compile(r"[0-9a-f]{16}")
_NAME_CHARS_RE = re.compile(r"[^A-Za-z0-9_-]+")
_MAX_STEM_LENGTH = 64
_MAX_NAME_INPUT = 255
_DEFAULT_STEM = "request"
_INBOX_KEYS = frozenset(("name", "content"))
_JSON_CONTENT_TYPE = "application/json; charset=utf-8"
_SECURITY_HEADERS = (
    ("X-Content-Type-Options", "nosniff"),
    ("Referrer-Policy", "no-referrer"),
    ("Cache-Control", "no-store"),
    ("Strict-Transport-Security", "max-age=31536000"),
)


class _Rejected(Exception):
    def __init__(self, status_code, message):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def token_hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def safe_name(raw_name):
    stem = raw_name[:_MAX_NAME_INPUT]
    if stem.lower().endswith(".md"):
        stem = stem[:-3]
    stem = _NAME_CHARS_RE.sub("-", stem).strip("-_")[:_MAX_STEM_LENGTH].strip("-_")
    return (stem or _DEFAULT_STEM) + ".md"


def is_file_id(value):
    return _ID_RE.fullmatch(value) is not None


def _status_dir(server):
    return server.store_dir / "status"


def _inbox_dir(server, guild):
    return server.store_dir / "inbox" / guild


class HubRequestHandler(http_server.BaseHTTPRequestHandler):
    server_version = "guild-realm"
    sys_version = ""
    timeout = _REQUEST_TIMEOUT_SECONDS

    def log_message(self, format_string, *args):
        return

    def setup(self):
        super().setup()
        self._deadline = threading.Timer(PRE_AUTH_DEADLINE_SECONDS, self._abort_connection)
        self._deadline.daemon = True
        self._deadline.start()

    def parse_request(self):
        parsed = super().parse_request()
        self._deadline.cancel()
        return parsed

    def finish(self):
        self._deadline.cancel()
        super().finish()

    def _abort_connection(self):
        try:
            self.connection.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass

    def _reply(self, status_code, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", _JSON_CONTENT_TYPE)
        self.send_header("Content-Length", str(len(body)))
        for name, value in _SECURITY_HEADERS:
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def _member(self):
        header = self.headers.get("Authorization")
        if header is None or not header.startswith("Bearer "):
            return None
        supplied = token_hash(header[len("Bearer ") :].strip()).encode("ascii")
        found = None
        for name, stored_hash in hubconfig.load()["members"].items():
            if hmac.compare_digest(supplied, str(stored_hash).encode("ascii", "replace")):
                found = name
        return found

    def _read_json_object(self, max_bytes):
        header = self.headers.get("Content-Type")
        if header is None or header.split(";")[0].strip().lower() != "application/json":
            raise _Rejected(415, "content type must be application/json")
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise _Rejected(411, "content length required")
        if not raw_length.isascii() or not raw_length.isdigit():
            raise _Rejected(400, "invalid content length")
        length = int(raw_length)
        if length > max_bytes:
            self.close_connection = True
            self.rfile.read(min(length, _OVERSIZE_DRAIN_BYTES))
            raise _Rejected(413, "request body too large")
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError, RecursionError):
            raise _Rejected(400, "body must be valid JSON") from None
        if not isinstance(payload, dict):
            raise _Rejected(400, "body must be a JSON object")
        return payload

    def _put_status(self, member):
        payload = self._read_json_object(STATUS_MAX_BODY)
        try:
            status.validate(payload, False)
        except GuildError:
            raise _Rejected(400, "invalid status") from None
        if payload["guild"] != member:
            raise _Rejected(403, "status guild must be the token's member")
        stored = dict(payload)
        stored["received_at"] = timeutil.to_iso(timeutil.utcnow())
        hubconfig.write_atomic(_status_dir(self.server) / (member + ".json"), json.dumps(stored).encode("utf-8"))
        self._reply(200, {"ok": True})

    def _get_status(self, member):
        entries = []
        for path in _status_dir(self.server).glob("*.json"):
            try:
                entries.append(status.validate(json.loads(path.read_text(encoding="utf-8")), True))
            except (ValueError, GuildError):
                continue
        entries.sort(key=lambda entry: entry["guild"])
        self._reply(200, {"realm": hubconfig.load()["name"], "guilds": entries})

    def _whoami(self, member):
        self._reply(200, {"member": member, "realm": hubconfig.load()["name"]})

    def _post_inbox(self, member, target):
        if target not in hubconfig.load()["members"]:
            raise _Rejected(404, "not found")
        payload = self._read_json_object(INBOX_MAX_BODY)
        name = payload.get("name")
        content = payload.get("content")
        if set(payload) != _INBOX_KEYS or not isinstance(name, str) or not isinstance(content, str):
            raise _Rejected(400, "name and content must be strings")
        try:
            data = content.encode("utf-8")
        except UnicodeEncodeError:
            raise _Rejected(400, "content must be UTF-8") from None
        if len(data) > CONTENT_MAX_BYTES:
            raise _Rejected(413, "content too large")
        with self.server.inbox_lock:
            inbox = paths.ensure_private_dir(_inbox_dir(self.server, target))
            senders = [json.loads(path.read_text(encoding="utf-8"))["from"] for path in inbox.glob("*.json")]
            if len(senders) >= INBOX_MAX_FILES or senders.count(member) >= INBOX_MAX_PER_SENDER:
                raise _Rejected(507, "inbox full")
            file_id = secrets.token_hex(8)
            meta = {
                "id": file_id,
                "from": member,
                "name": safe_name(name),
                "size": len(data),
                "sent_at": timeutil.to_iso(timeutil.utcnow()),
            }
            hubconfig.write_atomic(inbox / (file_id + ".md"), data)
            hubconfig.write_atomic(inbox / (file_id + ".json"), json.dumps(meta).encode("utf-8"))
        self._reply(201, {"id": file_id})

    def _list_inbox(self, member):
        inbox = _inbox_dir(self.server, member)
        metas = [json.loads(path.read_text(encoding="utf-8")) for path in inbox.glob("*.json")]
        metas.sort(key=lambda meta: meta["sent_at"])
        self._reply(200, {"files": metas})

    def _own_file(self, member, file_id):
        if not is_file_id(file_id):
            raise _Rejected(404, "not found")
        inbox = _inbox_dir(self.server, member)
        meta_path = inbox / (file_id + ".json")
        if not meta_path.is_file():
            raise _Rejected(404, "not found")
        return inbox, meta_path

    def _get_inbox_file(self, member, file_id):
        inbox, meta_path = self._own_file(member, file_id)
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["content"] = (inbox / (file_id + ".md")).read_bytes().decode("utf-8")
        self._reply(200, meta)

    def _delete_inbox_file(self, member, file_id):
        inbox, meta_path = self._own_file(member, file_id)
        (inbox / (file_id + ".md")).unlink(missing_ok=True)
        meta_path.unlink()
        self._reply(200, {"ok": True})

    def _routes(self):
        return (
            ("PUT", re.compile(r"^/status$"), self._put_status),
            ("GET", re.compile(r"^/status$"), self._get_status),
            ("GET", re.compile(r"^/whoami$"), self._whoami),
            ("POST", re.compile(r"^/inbox/([^/]+)$"), self._post_inbox),
            ("GET", re.compile(r"^/inbox$"), self._list_inbox),
            ("GET", re.compile(r"^/inbox/([^/]+)$"), self._get_inbox_file),
            ("DELETE", re.compile(r"^/inbox/([^/]+)$"), self._delete_inbox_file),
        )

    def _find_route(self, method):
        path_matched = False
        for route_method, pattern, handler in self._routes():
            match = pattern.match(self.path)
            if match is None:
                continue
            path_matched = True
            if route_method == method:
                return handler, match.groups()
        if path_matched:
            raise _Rejected(405, "method not allowed")
        raise _Rejected(404, "not found")

    def _dispatch(self, method):
        try:
            member = self._member()
            if member is None:
                raise _Rejected(401, "unauthorized")
            handler, arguments = self._find_route(method)
            handler(member, *arguments)
        except _Rejected as rejected:
            self._reply(rejected.status_code, {"error": rejected.message})
        except (GuildError, OSError, ValueError, RecursionError):
            self._reply(500, {"error": "internal error"})

    def do_GET(self):
        self._dispatch("GET")

    def do_PUT(self):
        self._dispatch("PUT")

    def do_POST(self):
        self._dispatch("POST")

    def do_DELETE(self):
        self._dispatch("DELETE")

    def do_HEAD(self):
        self._reply(405, {"error": "method not allowed"})

    def do_OPTIONS(self):
        self._reply(405, {"error": "method not allowed"})

    def do_PATCH(self):
        self._reply(405, {"error": "method not allowed"})


class _HubServer(http_server.ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, handler_class, max_connections):
        super().__init__(address, handler_class)
        self.connection_slots = threading.BoundedSemaphore(max_connections)

    def process_request(self, request, client_address):
        if not self.connection_slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        super().process_request(request, client_address)

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.connection_slots.release()

    def handle_error(self, request, client_address):
        error = sys.exc_info()[1]
        if isinstance(error, (ssl.SSLError, ConnectionError, TimeoutError)):
            return
        sys.stderr.write("guild realm hub: request failed: {}\n".format(type(error).__name__))


def make_server(config):
    server = _HubServer((config["bind"], config["port"]), HubRequestHandler, MAX_CONNECTIONS)
    server.store_dir = paths.realm_hub_store_dir()
    server.inbox_lock = threading.Lock()
    paths.ensure_private_dir(server.store_dir)
    paths.ensure_private_dir(_status_dir(server))
    paths.ensure_private_dir(server.store_dir / "inbox")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.load_cert_chain(config["cert"], config["key"])
    server.socket = context.wrap_socket(server.socket, server_side=True, do_handshake_on_connect=False)
    return server


def serve_forever(config):
    server = make_server(config)
    print("guild realm hub: https://{}:{}/".format(config["bind"], server.server_address[1]), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
