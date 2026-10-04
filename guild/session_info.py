import json
import os


def _pid_alive(pid):
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except PermissionError:
        return True
    except (ProcessLookupError, OverflowError, OSError):
        return False
    return True


def current_session_id():
    return os.environ.get("CLAUDE_CODE_SESSION_ID")


def read_session_name(sessions_dir, session_id):
    if not sessions_dir.is_dir():
        return None
    for entry in sessions_dir.glob("*.json"):
        try:
            data = json.loads(entry.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if data.get("sessionId") == session_id:
            return data.get("name")
    return None


def running_session_ids(sessions_dir):
    if not sessions_dir.is_dir():
        return set()
    ids = set()
    for entry in sessions_dir.glob("*.json"):
        try:
            data = json.loads(entry.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        session_id = data.get("sessionId")
        if session_id is not None:
            ids.add(session_id)
    return ids


def live_session_ids(sessions_dir):
    if not sessions_dir.is_dir():
        return set()
    ids = set()
    for entry in sessions_dir.glob("*.json"):
        try:
            data = json.loads(entry.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        session_id = data.get("sessionId")
        if session_id is not None and _pid_alive(data.get("pid")):
            ids.add(session_id)
    return ids


def resolve_session_id(sessions_dir, session_name):
    if not sessions_dir.is_dir():
        return None
    for entry in sessions_dir.glob("*.json"):
        try:
            data = json.loads(entry.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if data.get("name") == session_name:
            return data.get("sessionId")
    return None
