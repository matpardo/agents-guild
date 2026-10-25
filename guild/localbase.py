import glob
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from guild import timeutil

_ORIGIN = "origin"
_URL_SEPARATOR = re.compile(r"[/:]")
_GIT_SUFFIX = ".git"
_BRANCH_PREFIX = "branch refs/heads/"
_WORKTREE_PREFIX = "worktree "
_PRUNABLE_PREFIX = "prunable"
_NO_ORIGIN_HEAD = "no origin/HEAD (git remote set-head origin --auto)"
_CANNOT_COMPARE = "cannot compare"


def _git(path, args):
    environment = dict(os.environ)
    environment["GIT_TERMINAL_PROMPT"] = "0"
    try:
        result = subprocess.run(["git", "-C", str(path)] + args, capture_output=True, text=True, env=environment)
    except OSError as error:
        return 1, "", str(error)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def origin_head_ref(target_dir):
    code, out, _ = _git(target_dir, ["symbolic-ref", "--short", "refs/remotes/origin/HEAD"])
    if code != 0:
        return None
    return out or None


def _repo_slug(remote_url):
    trimmed = remote_url.rstrip("/")
    if trimmed.endswith(_GIT_SUFFIX):
        trimmed = trimmed[: -len(_GIT_SUFFIX)]
    parts = [part for part in _URL_SEPARATOR.split(trimmed) if part]
    if len(parts) < 2:
        return None
    return "{}/{}".format(parts[-2], parts[-1])


def is_main_checkout(directory):
    return (Path(directory) / ".git").is_dir()


def origin_repo_slug(directory):
    code, out, _ = _git(directory, ["config", "--get", "remote.origin.url"])
    if code != 0:
        return None
    return _repo_slug(out)


def _clone_repo(directory, repos):
    slug = origin_repo_slug(directory)
    if slug not in repos:
        return None
    return slug


def _checkout_candidates(match):
    if is_main_checkout(match):
        return [match]
    if not os.path.isdir(match):
        return []
    children = sorted(os.path.join(match, name) for name in os.listdir(match))
    return [child for child in children if is_main_checkout(child)]


def locate_clones(project):
    repos = project["github"]["repos"]
    clones = []
    seen = set()
    for pattern in project["paths"]:
        for match in sorted(glob.glob(str(Path(pattern).expanduser()))):
            for candidate in _checkout_candidates(match):
                if candidate in seen:
                    continue
                seen.add(candidate)
                repo = _clone_repo(candidate, repos)
                if repo is None:
                    continue
                clones.append({"repo": repo, "path": candidate})
    return clones


def base_branch(clone_path):
    ref = origin_head_ref(clone_path)
    if ref is None:
        return None
    return ref.split("/", 1)[1]


def _count(clone_path, revision_range):
    code, out, _ = _git(clone_path, ["rev-list", "--count", revision_range])
    if code != 0:
        return None
    return int(out)


def repo_clones(projects):
    clones = {}
    for project in projects:
        for clone in locate_clones(project):
            if clone["repo"] in clones:
                continue
            clones[clone["repo"]] = {"path": clone["path"], "base": base_branch(clone["path"])}
    return clones


def branch_behind(clone_path, branch, base):
    return _count(clone_path, "{}/{}..{}/{}".format(_ORIGIN, branch, _ORIGIN, base))


def _commits_behind(clone_path, base):
    return _count(clone_path, "{}..{}/{}".format(base, _ORIGIN, base))


def _commits_ahead(clone_path, base):
    return _count(clone_path, "{}/{}..{}".format(_ORIGIN, base, base))


def _fetched_at(clone_path):
    code, out, _ = _git(clone_path, ["rev-parse", "--git-path", "FETCH_HEAD"])
    if code != 0:
        return None
    try:
        mtime = (Path(clone_path) / out).stat().st_mtime
    except OSError:
        return None
    return timeutil.to_iso(datetime.fromtimestamp(mtime, timezone.utc))


def _drift_entry(repo, base, behind, ahead, fetched_at, error):
    return {"repo": repo, "base": base, "behind": behind, "ahead": ahead, "fetched_at": fetched_at, "error": error}


def _clone_drift(clone):
    base = base_branch(clone["path"])
    if base is None:
        return _drift_entry(clone["repo"], None, None, None, None, _NO_ORIGIN_HEAD)
    fetched_at = _fetched_at(clone["path"])
    behind = _commits_behind(clone["path"], base)
    ahead = _commits_ahead(clone["path"], base)
    if behind is None or ahead is None:
        return _drift_entry(clone["repo"], base, None, None, fetched_at, _CANNOT_COMPARE)
    return _drift_entry(clone["repo"], base, behind, ahead, fetched_at, None)


def base_drift(project):
    return [_clone_drift(clone) for clone in locate_clones(project)]


def fetch_base_mutating_git(clone_path, base):
    code, _, error = _git(clone_path, ["fetch", _ORIGIN, base])
    if code != 0:
        return error
    return None


def behind_warning_lines(project):
    return [
        "local {} of {} is {} commits behind {}/{}".format(
            entry["base"], entry["repo"], entry["behind"], _ORIGIN, entry["base"]
        )
        for entry in base_drift(project)
        if entry["error"] is None and entry["behind"]
    ]


def _checked_out_worktree(clone_path, base):
    code, out, _ = _git(clone_path, ["worktree", "list", "--porcelain"])
    if code != 0:
        return None
    current = None
    for line in out.splitlines():
        if line.startswith(_WORKTREE_PREFIX):
            current = line[len(_WORKTREE_PREFIX) :]
        elif line == _BRANCH_PREFIX + base:
            return current
    return None


def _worktree_block(lines, is_main):
    entry = {"path": lines[0][len(_WORKTREE_PREFIX) :], "branch": None, "is_main": is_main, "prunable": False}
    for line in lines[1:]:
        if line.startswith(_BRANCH_PREFIX):
            entry["branch"] = line[len(_BRANCH_PREFIX) :]
        elif line == _PRUNABLE_PREFIX or line.startswith(_PRUNABLE_PREFIX + " "):
            entry["prunable"] = True
    return entry


def worktrees(clone_path):
    code, out, _ = _git(clone_path, ["worktree", "list", "--porcelain"])
    if code != 0:
        return []
    entries = []
    for block in out.split("\n\n"):
        lines = [line for line in block.splitlines() if line]
        if not lines or not lines[0].startswith(_WORKTREE_PREFIX):
            continue
        entries.append(_worktree_block(lines, not entries))
    return entries


def origin_tip(clone_path, base):
    code, out, _ = _git(clone_path, ["rev-parse", "{}/{}".format(_ORIGIN, base)])
    if code != 0:
        return None
    return out


def _fast_forward_checked_out_mutating_git(worktree, base):
    code, out, _ = _git(worktree, ["status", "--porcelain"])
    if code != 0:
        return "cannot read status of {}".format(worktree)
    if out:
        return "worktree {} has uncommitted changes".format(worktree)
    code, _, error = _git(worktree, ["merge", "--ff-only", "{}/{}".format(_ORIGIN, base)])
    if code != 0:
        return "fast-forward failed in {}: {}".format(worktree, error)
    return None


def fast_forward_base_mutating_git(clone_path, base):
    code, _, error = _git(clone_path, ["fetch", _ORIGIN])
    if code != 0:
        return {"behind": None, "reason": "fetch failed: {}".format(error)}
    behind = _commits_behind(clone_path, base)
    if not behind:
        return {"behind": 0, "reason": None}
    ahead = _commits_ahead(clone_path, base)
    if ahead:
        return {"behind": behind, "reason": "diverged, {} local commits not in origin".format(ahead)}
    worktree = _checked_out_worktree(clone_path, base)
    if worktree is not None:
        return {"behind": behind, "reason": _fast_forward_checked_out_mutating_git(worktree, base)}
    code, _, error = _git(clone_path, ["fetch", _ORIGIN, "{}:{}".format(base, base)])
    if code != 0:
        return {"behind": behind, "reason": "fetch into {} failed: {}".format(base, error)}
    return {"behind": behind, "reason": None}
