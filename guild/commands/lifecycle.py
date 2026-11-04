from guild import config, db, events, localbase, locking
from guild.commands import notice as notice_commands
from guild.errors import GuildError

_NOTICE_TTL = "12h"
_NOTICE_TEMPLATE = "lifecycle {} failed for {} ({}): see guild history"
_LOCK_DIR_NAME = "lifecycle"
_SECONDS_PER_MINUTE = 60
_NOTIFYING_STATUSES = ("failed", "timeout", "error")


def _project_for_repo(projects, repo):
    for project in projects:
        if repo in project["github"]["repos"]:
            return project
    return None


def triggers_by_project(projects, triggers):
    groups = {}
    for event_kind, repo, number in triggers:
        project = _project_for_repo(projects, repo)
        if project is None or event_kind not in project.get("lifecycle", {}):
            continue
        groups.setdefault((project["name"], event_kind), {"project": project, "triggers": []})["triggers"].append(
            (repo, number)
        )
    return [
        {
            "project": groups[key]["project"],
            "event": key[1],
            "triggers": sorted(groups[key]["triggers"]),
        }
        for key in sorted(groups)
    ]


def checkout_for(project, repo):
    for clone in localbase.locate_clones(project):
        if clone["repo"] == repo:
            return clone["path"]
    return None


def _record_ran(ctx, payload):
    with db.writing(ctx.conn):
        events.record(
            ctx.conn,
            ctx.now,
            ctx.origin,
            None,
            ctx.session_id,
            payload["project"],
            "lifecycle.ran",
            "local",
            payload,
        )


def _failure_detail(payload):
    if payload["status"] == "failed":
        return "exit {}".format(payload["exit_code"])
    return payload["status"]


def _notify_failure(ctx, payload):
    announces = "lifecycle:{}:{}:{}".format(payload["project"], payload["event"], payload["triggers"][0])
    if notice_commands.announced(ctx.conn, announces):
        return
    text = _NOTICE_TEMPLATE.format(payload["event"], payload["project"], _failure_detail(payload))
    notice_commands.create_announcing(ctx, None, text, "project:{}".format(payload["project"]), _NOTICE_TTL, announces)


def _status_of(entry, result):
    if result["error"] is not None:
        return "error"
    if result["timed_out"]:
        return "timeout"
    if result["exit_code"] == 0 or result["exit_code"] in entry.get("ok_exit_codes", ()):
        return "ok"
    return "failed"


def _base_payload(project, event_kind, repo, trigger_refs, cwd):
    return {
        "project": project["name"],
        "event": event_kind,
        "repo": repo,
        "triggers": trigger_refs,
        "argv": project["lifecycle"][event_kind]["command"],
        "cwd": cwd,
        "status": None,
        "exit_code": None,
        "duration_ms": 0,
        "output_tail": "",
        "reason": None,
    }


def _finish(ctx, payload):
    _record_ran(ctx, payload)
    if payload["status"] in _NOTIFYING_STATUSES:
        _notify_failure(ctx, payload)
    return payload


def _execute(project, event_kind, payload, runner):
    entry = project["lifecycle"][event_kind]
    result = runner(entry["command"], payload["cwd"], entry["timeout_minutes"] * _SECONDS_PER_MINUTE)
    payload["status"] = _status_of(entry, result)
    payload["exit_code"] = result["exit_code"]
    payload["duration_ms"] = result["duration_ms"]
    payload["output_tail"] = result["output"]
    payload["reason"] = result["error"]


def run_group(ctx, project, event_kind, repo, trigger_refs, runner):
    cwd = checkout_for(project, repo)
    payload = _base_payload(project, event_kind, repo, trigger_refs, cwd)
    if cwd is None:
        payload["status"] = "error"
        payload["reason"] = "no checkout"
        return _finish(ctx, payload)
    lock_file = "{}-{}.lock".format(project["name"], event_kind)
    with locking.try_lock(ctx.state_dir / _LOCK_DIR_NAME, lock_file) as acquired:
        if not acquired:
            payload["status"] = "skipped"
            payload["reason"] = "locked"
            return _finish(ctx, payload)
        _execute(project, event_kind, payload, runner)
    return _finish(ctx, payload)


def _record_crash(ctx, project, event_kind, repo, trigger_refs, error):
    payload = _base_payload(project, event_kind, repo, trigger_refs, checkout_for(project, repo))
    payload["status"] = "error"
    payload["reason"] = "{}: {}".format(type(error).__name__, error)
    _finish(ctx, payload)


def _run_group_guarded(ctx, group, runner):
    repo = group["triggers"][0][0]
    refs = ["{}#{}".format(trigger_repo, number) for trigger_repo, number in group["triggers"]]
    try:
        run_group(ctx, group["project"], group["event"], repo, refs, runner)
    except Exception as error:
        _record_crash(ctx, group["project"], group["event"], repo, refs, error)


def run_sync_triggers(ctx, projects, triggers, runner):
    for group in triggers_by_project(projects, triggers):
        _run_group_guarded(ctx, group, runner)


def _resolve_repo(project, repo):
    if repo is not None:
        return repo
    clones = localbase.locate_clones(project)
    if not clones:
        raise GuildError("project '{}' has no local clone: pass --repo".format(project["name"]), 1)
    if len(clones) > 1:
        raise GuildError("project '{}' has several clones: pass --repo".format(project["name"]), 1)
    return clones[0]["repo"]


def _duration_label(duration_ms):
    return "{:.1f}s".format(duration_ms / 1000)


def _dry_run_line(project, event_kind, repo):
    cwd = checkout_for(project, repo)
    if cwd is None:
        raise GuildError("project '{}' has no local clone of {}".format(project["name"], repo), 1)
    entry = project["lifecycle"][event_kind]
    return "would run: {} (cwd {}, timeout {}m)".format(" ".join(entry["command"]), cwd, entry["timeout_minutes"])


def _outcome_line(payload):
    prefix = "lifecycle {}:".format(payload["event"])
    if payload["status"] == "skipped":
        return "{} skipped: {}".format(prefix, payload["reason"])
    if payload["status"] == "error":
        return "{} error ({})".format(prefix, payload["reason"])
    detail = "exit {}, {}".format(payload["exit_code"], _duration_label(payload["duration_ms"]))
    if payload["status"] == "timeout":
        detail = "timeout, {}".format(_duration_label(payload["duration_ms"]))
    return "{} {} ({})".format(prefix, payload["status"], detail)


def run_manual(ctx, event_kind, repo, dry_run, runner):
    project_name = config.require_project(ctx.cwd, ctx.projects_dir)
    project = config.load_project(ctx.projects_dir, project_name)
    if event_kind not in project.get("lifecycle", {}):
        raise GuildError("project '{}' has no lifecycle.{} configured".format(project_name, event_kind), 1)
    resolved_repo = _resolve_repo(project, repo)
    if dry_run:
        return _dry_run_line(project, event_kind, resolved_repo)
    payload = run_group(ctx, project, event_kind, resolved_repo, ["manual"], runner)
    line = _outcome_line(payload)
    if payload["status"] in _NOTIFYING_STATUSES:
        raise GuildError(line, 1)
    return line
