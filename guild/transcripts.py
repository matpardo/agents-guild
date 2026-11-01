import json
import re
from pathlib import Path


def find_transcript(projects_dir, session_id):
    if session_id is None:
        return None
    matches = sorted(projects_dir.glob("*/{}.jsonl".format(session_id)))
    if not matches:
        return None
    return matches[0]


_LAUNCH_PATTERN = re.compile(r"Command running in background with ID: (\w+)")
_NOTIFICATION_PATTERN = re.compile(
    r"<task-id>(\w+)</task-id>.*?<status>(completed|failed|killed|stopped)</status>", re.S
)


def _message_content(line):
    try:
        entry = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(entry, dict) or entry.get("type") != "user":
        return None
    message = entry.get("message")
    if not isinstance(message, dict):
        return None
    return message.get("content")


def _launch_texts(content):
    if not isinstance(content, list):
        return []
    return [
        block["content"]
        for block in content
        if isinstance(block, dict) and block.get("type") == "tool_result" and isinstance(block.get("content"), str)
    ]


def pending_background_ids(transcript_path):
    if not transcript_path:
        return set()
    try:
        lines = Path(transcript_path).read_text().splitlines()
    except OSError:
        return set()
    launched = set()
    finished = set()
    for line in lines:
        content = _message_content(line)
        if isinstance(content, str):
            finished.update(match.group(1) for match in _NOTIFICATION_PATTERN.finditer(content))
        for text in _launch_texts(content):
            launched.update(_LAUNCH_PATTERN.findall(text))
    return launched - finished
