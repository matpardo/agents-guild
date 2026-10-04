import os
import re
from pathlib import Path

from guild import localbase
from guild.resources import sizes

CATEGORY_WORKTREE = "worktree"
_DU_TIMEOUT_SECONDS = 300
_GLOB_MAGIC_RE = re.compile(r"[*?\[]")
_EXCLUDE_ESCAPE_RE = re.compile(r"([\\*?\[])")
_FLAGGED_LIFECYCLES = {"merged": "merged", "closed": "closed"}
_LATEST_PR_LIFECYCLE_SQL = (
    "SELECT lifecycle FROM prs WHERE repo = ? AND branch = ? ORDER BY number DESC LIMIT 1"
)


class Deadline:
    def __init__(self, clock, limit_seconds):
        self._clock = clock
        self._limit_seconds = limit_seconds
        self._started = clock()

    def reached(self):
        return self._clock() - self._started >= self._limit_seconds


def _escape_exclude(path):
    return _EXCLUDE_ESCAPE_RE.sub(r"\\\1", path)


def _du_argv(path, excludes):
    argv = ["du", "-s", "-B1", "-x"]
    argv.extend("--exclude={}".format(_escape_exclude(exclude)) for exclude in excludes)
    argv.append(path)
    return argv


def _accepts(result):
    if result["exit_code"] == 0:
        return True
    return result["exit_code"] == 1 and bool(result["stdout"].strip())


def du_bytes(path, excludes, runner, deadline):
    if not os.path.isdir(path):
        return None, "missing"
    if deadline.reached():
        return None, "skipped"
    result = runner(_du_argv(path, excludes), _DU_TIMEOUT_SECONDS)
    if result["timed_out"]:
        return None, "skipped"
    if result["error"] is not None or not _accepts(result):
        return None, "unavailable"
    size = sizes.parse_du_output(result["stdout"])
    if size is None:
        return None, "unavailable"
    return size, "ok"


def _literal_prefix(pattern):
    expanded = str(Path(pattern).expanduser())
    kept = []
    for component in expanded.split(os.sep):
        if _GLOB_MAGIC_RE.search(component):
            break
        kept.append(component)
    return os.sep.join(kept) or os.sep


def _clone_entries(clone):
    entries = localbase.worktrees(clone["path"])
    if entries:
        return entries
    return [{"path": clone["path"], "branch": None, "is_main": True, "prunable": False}]


def _project_entries(project, seen_paths):
    entries = []
    checkouts = set()
    prefixes = {_literal_prefix(pattern) for pattern in project["paths"]}
    for clone in localbase.locate_clones(project):
        checkouts.add(clone["path"])
        for worktree in _clone_entries(clone):
            checkouts.add(worktree["path"])
            if worktree["path"] in seen_paths:
                continue
            seen_paths.add(worktree["path"])
            entry = dict(worktree)
            entry["project"] = project["name"]
            entry["repo"] = clone["repo"]
            entries.append(entry)
    return entries, sorted(prefixes | checkouts), sorted(checkouts)


def discover(projects):
    entries = []
    roots = {}
    checkouts = {}
    seen_paths = set()
    for project in sorted(projects, key=lambda candidate: candidate["name"]):
        project_entries, project_roots, project_checkouts = _project_entries(project, seen_paths)
        entries.extend(project_entries)
        roots[project["name"]] = project_roots
        checkouts[project["name"]] = project_checkouts
    return {"entries": entries, "roots": roots, "checkouts": checkouts}


def _is_strictly_inside(path, parent):
    return path != parent and path.startswith(parent.rstrip(os.sep) + os.sep)


def _nested_paths(entry, entries):
    return [other["path"] for other in entries if _is_strictly_inside(other["path"], entry["path"])]


def _flag(conn, entry):
    if entry["is_main"] or entry["branch"] is None:
        return ""
    row = conn.execute(_LATEST_PR_LIFECYCLE_SQL, (entry["repo"], entry["branch"])).fetchone()
    if row is None:
        return ""
    return _FLAGGED_LIFECYCLES.get(row["lifecycle"], "")


def _worktree_row(conn, entry, entries, runner, deadline):
    detail = entry["branch"] or ""
    if entry["prunable"]:
        return [CATEGORY_WORKTREE, entry["path"], None, "missing", "", detail]
    size, state = du_bytes(entry["path"], _nested_paths(entry, entries), runner, deadline)
    if state == "missing":
        return [CATEGORY_WORKTREE, entry["path"], None, "missing", "", detail]
    return [CATEGORY_WORKTREE, entry["path"], size, state, _flag(conn, entry), detail]


def sample_worktrees(conn, entries, runner, deadline):
    return [(entry["project"], _worktree_row(conn, entry, entries, runner, deadline)) for entry in entries]
