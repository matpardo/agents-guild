import atexit
import json
import subprocess
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
_servers = {}


def _server(harness_name):
    server = _servers.get(harness_name)
    if server is not None:
        return server
    server = subprocess.Popen(
        ["node", str(_TESTS_DIR / harness_name)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
    )
    _servers[harness_name] = server
    return server


def request(harness_name, payload):
    server = _server(harness_name)
    server.stdin.write(json.dumps(payload) + "\n")
    server.stdin.flush()
    line = server.stdout.readline()
    if not line:
        raise RuntimeError(harness_name + " exited without a reply")
    return json.loads(line)


def _stop_all():
    for server in _servers.values():
        server.stdin.close()
        server.wait(timeout=10)


atexit.register(_stop_all)
