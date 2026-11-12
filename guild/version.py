import os
import subprocess
from pathlib import Path

_UNKNOWN = "unknown"

REPO_ROOT = Path(__file__).resolve().parent.parent


def describe(repo_root):
    environment = dict(os.environ)
    environment["GIT_TERMINAL_PROMPT"] = "0"
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "describe", "--tags", "--always", "--dirty"],
            capture_output=True,
            text=True,
            env=environment,
        )
    except OSError:
        return _UNKNOWN
    if result.returncode != 0:
        return _UNKNOWN
    return result.stdout.strip() or _UNKNOWN
