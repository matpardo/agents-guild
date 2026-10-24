import hmac
import http.client
import json
import ssl
from urllib.parse import urlsplit

from guild.errors import GuildError
from guild.realm import pin

MAX_RESPONSE_BYTES = 2 * 1024 * 1024
_TIMEOUT_SECONDS = 10


def parse_url(url):
    parts = urlsplit(url)
    try:
        port = parts.port
    except ValueError:
        raise GuildError("invalid realm url: bad port", 1)
    if parts.scheme != "https" or not parts.hostname:
        raise GuildError("invalid realm url: use https://host[:port]", 1)
    if parts.path not in ("", "/") or parts.query or parts.fragment or parts.username or parts.password:
        raise GuildError("invalid realm url: use https://host[:port] only", 1)
    return parts.hostname, port if port is not None else 443


def _context():
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


def _connect_pinned(config):
    host, port = parse_url(config["url"])
    connection = http.client.HTTPSConnection(host, port, context=_context(), timeout=_TIMEOUT_SECONDS)
    try:
        connection.connect()
        got = pin.fingerprint(connection.sock.getpeercert(binary_form=True))
    except (OSError, http.client.HTTPException) as error:
        connection.close()
        raise GuildError("realm hub unreachable: {}".format(type(error).__name__), 1)
    if not hmac.compare_digest(got.encode("ascii"), config["fingerprint"].encode("ascii")):
        connection.close()
        raise GuildError(
            "realm hub fingerprint mismatch: expected {}, got {}".format(config["fingerprint"], got), 1
        )
    return connection


def _read_json(response):
    raw = response.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise GuildError("realm hub response too large", 1)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise GuildError("realm hub sent an invalid response", 1)
    if not isinstance(payload, dict):
        raise GuildError("realm hub sent an invalid response", 1)
    return payload


def request(config, method, path, body):
    connection = _connect_pinned(config)
    headers = {"Authorization": "Bearer " + config["token"]}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    try:
        connection.request(method, path, body=data, headers=headers)
        response = connection.getresponse()
        payload = _read_json(response)
        status_code = response.status
    except (OSError, http.client.HTTPException) as error:
        raise GuildError("realm hub request failed: {}".format(type(error).__name__), 1)
    finally:
        connection.close()
    if not 200 <= status_code < 300:
        message = payload.get("error")
        raise GuildError("realm hub refused ({}): {}".format(status_code, message if isinstance(message, str) else "no reason"), 1)
    return payload
