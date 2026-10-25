import os
from pathlib import Path

from guild import config, db, events, locking, paths
from guild.errors import GuildError
from guild.resources import claude_dirs, disk, docker, machine

_LOCK_FILE = "collect.lock"
_LOCK_DIR_NAME = "resources"
_ALREADY_RUNNING = "collect already running"
_MEMINFO_PATH = Path("/proc/meminfo")
_DISK_ROOT = Path("/")
_KIND = "resources.sampled"
_VISIBILITY = "local"


def _docker_marker(reason):
    return [docker.MARKER_CATEGORY, "-", None, "unavailable", "", reason]


def _docker_rows(scan, found):
    if not scan["ok"]:
        return {None: [_docker_marker(scan["reason"])]}
    return docker.attribute(scan["df"], found["roots"], found["checkouts"], os.path.isdir)


def _measure(ctx, projects, runner, deadline):
    found = disk.discover(projects)
    sampled = disk.sample_worktrees(ctx.conn, found["entries"], runner, deadline)
    sampled.extend(
        claude_dirs.sample(found["entries"], paths.claude_scratch_dir(), paths.claude_projects_dir(), runner, deadline)
    )
    scan = docker.scan(runner)
    rows_by_project = {project["name"]: [] for project in projects}
    for project, row in sampled:
        rows_by_project[project].append(row)
    for project, rows in _docker_rows(scan, found).items():
        rows_by_project.setdefault(project, []).extend(rows)
    snapshot = machine.snapshot(_DISK_ROOT, _MEMINFO_PATH, paths.db_path())
    snapshot["docker"] = scan["totals"]
    return rows_by_project, snapshot, scan


def _payloads(rows_by_project, snapshot):
    payloads = []
    for project in sorted(rows_by_project, key=lambda name: (name is None, name or "")):
        rows = sorted(rows_by_project[project], key=lambda row: (row[0], row[1]))
        payloads.append((project, {"items": rows, "machine": snapshot}))
    return payloads


def _record(ctx, payloads):
    with db.writing(ctx.conn):
        for project, payload in payloads:
            events.record(ctx.conn, ctx.now, ctx.origin, None, None, project, _KIND, _VISIBILITY, payload)


def _plural(count, word):
    if count == 1:
        return "{} {}".format(count, word)
    return "{} {}s".format(count, word)


def _summary(payloads, scan, elapsed_seconds):
    rows = [row for _, payload in payloads for row in payload["items"]]
    named_projects = [project for project, _ in payloads if project is not None]
    line = "sampled {}, {} in {}s".format(
        _plural(len(named_projects), "project"), _plural(len(rows), "item"), elapsed_seconds
    )
    unavailable = []
    if not scan["ok"]:
        unavailable.append("docker ({})".format(scan["reason"]))
    other_unavailable = [row for row in rows if row[3] == "unavailable" and row[0] != docker.MARKER_CATEGORY]
    if other_unavailable:
        unavailable.append(_plural(len(other_unavailable), "item"))
    skipped = [row for row in rows if row[3] == "skipped"]
    if unavailable:
        line += "; unavailable: {}".format(", ".join(unavailable))
    if skipped:
        line += "; skipped: {}".format(len(skipped))
    return line


def collect(ctx, runner, clock, deadline_seconds):
    projects = config.load_all_projects(ctx.projects_dir)
    if not projects:
        raise GuildError("no projects configured", 1)
    with locking.try_lock(ctx.state_dir / _LOCK_DIR_NAME, _LOCK_FILE) as acquired:
        if not acquired:
            return _ALREADY_RUNNING
        started = clock()
        deadline = disk.Deadline(clock, deadline_seconds)
        rows_by_project, snapshot, scan = _measure(ctx, projects, runner, deadline)
        payloads = _payloads(rows_by_project, snapshot)
        _record(ctx, payloads)
        return _summary(payloads, scan, int(clock() - started))
