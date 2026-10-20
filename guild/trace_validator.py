import json
import os
import re
import tempfile
from pathlib import Path

from guild import pii
from guild.errors import GuildError

_HEX_SHA = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
_PLACEHOLDER = re.compile(r"\{(head_sha|pr|comments_file)\}")
_REASON_MAX = 200


def _argv(command, values):
    return [_PLACEHOLDER.sub(lambda match: values[match.group(1)], part) for part in command]


def _screened(reason, project, exit_code):
    withheld = "exit {} (reason withheld by the screen)".format(exit_code)
    try:
        pii.validate_field(reason, "trace validator reason", _REASON_MAX, project.get("pii_patterns") or [])
    except GuildError:
        return withheld
    if pii.looks_instruction_like(reason):
        return withheld
    return reason


def _reason(project, result):
    lines = [line.strip() for line in result["output"].splitlines() if line.strip()]
    if not lines:
        return "exit {}".format(result["exit_code"])
    return _screened(lines[-1][:_REASON_MAX], project, result["exit_code"])


def _verdict(project, result, timeout_seconds):
    if result["timed_out"]:
        return None, "validator timed out after {}s".format(timeout_seconds)
    if result["error"] is not None:
        return None, "validator could not start"
    if result["exit_code"] == 0:
        return 1, None
    return 0, _reason(project, result)


def check(project, cwd, number, head_sha, discussion, runner):
    if not isinstance(head_sha, str) or not _HEX_SHA.fullmatch(head_sha):
        return None, "head sha is not a hex commit id"
    if type(number) is not int or number <= 0:
        return None, "pr number is not an integer"
    validator = project["human_ready"]["trace_validator"]
    try:
        handle, path = tempfile.mkstemp(prefix="guild-trace-", suffix=".json")
    except OSError:
        return None, "validator could not run"
    try:
        try:
            with os.fdopen(handle, "w") as comments_file:
                json.dump(discussion, comments_file)
        except OSError:
            return None, "validator could not run"
        values = {"head_sha": head_sha, "pr": str(number), "comments_file": path}
        result = runner(_argv(validator["command"], values), cwd, validator["timeout_seconds"])
        return _verdict(project, result, validator["timeout_seconds"])
    except (ValueError, TypeError):
        return None, "validator could not start"
    finally:
        Path(path).unlink(missing_ok=True)
