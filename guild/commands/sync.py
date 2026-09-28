import json

from guild import config, db, events, timeutil
from guild.adapters import github, sdd
from guild.commands import notice as notice_commands
from guild.errors import GuildError

_SDD_PATTERN_KEYS = ("task_heading", "key_ref", "deps_line", "status_line")

_FAILING_CONCLUSIONS = ("FAILURE", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED")
_SUCCESS_CONCLUSION = "SUCCESS"


def _count_checks(rollup):
    failing = 0
    passing = 0
    for entry in rollup or []:
        conclusion = entry.get("conclusion")
        if conclusion == _SUCCESS_CONCLUSION:
            passing += 1
        elif conclusion in _FAILING_CONCLUSIONS:
            failing += 1
    return failing, passing


def _lifecycle_from_gh(current_lifecycle, gh_data):
    if gh_data.get("mergedAt"):
        return "merged"
    if gh_data.get("state") == "CLOSED":
        return "closed"
    return current_lifecycle


def _sync_pr(ctx, row):
    gh_data = github.pr_view(
        ctx.cwd,
        row["repo"],
        row["number"],
        [
            "state", "isDraft", "mergedAt", "headRefName", "title", "statusCheckRollup",
            "reviewDecision", "mergeable", "comments", "reviews",
        ],
    )
    failing, passing = _count_checks(gh_data.get("statusCheckRollup"))
    lifecycle = _lifecycle_from_gh(row["lifecycle"], gh_data)
    review_comment_count = len(gh_data.get("comments") or []) + len(gh_data.get("reviews") or [])
    with db.writing(ctx.conn):
        events.record(
            ctx.conn,
            ctx.now,
            ctx.origin,
            row["party"],
            ctx.session_id,
            None,
            "pr.synced",
            "guild",
            {
                "repo": row["repo"],
                "number": row["number"],
                "gh_state": gh_data.get("state"),
                "gh_draft": gh_data.get("isDraft"),
                "branch": gh_data.get("headRefName"),
                "title": gh_data.get("title"),
                "checks_failing": failing,
                "checks_passing": passing,
                "lifecycle": lifecycle,
                "mergeable": gh_data.get("mergeable"),
                "review_comment_count": review_comment_count,
                "synced_at": timeutil.to_iso(ctx.now),
            },
        )


def _close_met_notices(ctx):
    rows = notice_commands.active_notices(ctx.conn, ctx.now)
    for row in rows:
        if row["until_condition"] is None:
            continue
        condition = json.loads(row["until_condition"])
        pr_row = ctx.conn.execute(
            "SELECT lifecycle FROM prs WHERE repo = ? AND number = ?",
            (condition["repo"], condition["number"]),
        ).fetchone()
        if pr_row is None or pr_row["lifecycle"] != condition["state"]:
            continue
        with db.writing(ctx.conn):
            events.record(
                ctx.conn,
                ctx.now,
                ctx.origin,
                row["party"],
                ctx.session_id,
                None,
                "notice.closed",
                "guild",
                {"id": row["id"]},
            )


def _sync_gh(ctx):
    rows = ctx.conn.execute(
        "SELECT * FROM prs WHERE lifecycle NOT IN ('merged', 'closed')"
    ).fetchall()
    failures = []
    for row in rows:
        try:
            _sync_pr(ctx, row)
        except github.GhCommandError as error:
            failures.append("{}#{}: {}".format(row["repo"], row["number"], error))
    _close_met_notices(ctx)
    return failures


def _sdd_patterns(sdd_config):
    patterns = {key: sdd_config[key] for key in _SDD_PATTERN_KEYS}
    if "order_list" in sdd_config:
        patterns["order_list"] = sdd_config["order_list"]
    return patterns


def _sync_epic_file(ctx, project, epic, path, patterns):
    tasks = sdd.parse_tasks_file(path, patterns)
    if tasks is None:
        raise GuildError("no matching task headings", 1)
    with db.writing(ctx.conn):
        events.record(
            ctx.conn,
            ctx.now,
            ctx.origin,
            None,
            ctx.session_id,
            project,
            "epic.synced",
            "local",
            {"project": project, "epic": epic, "sdd_path": str(path), "tasks": tasks},
        )


def _sync_sdd(ctx):
    project = config.require_project(ctx.cwd, ctx.projects_dir)
    project_data = config.load_project(ctx.projects_dir, project)
    sdd_config = project_data.get("sdd")
    if sdd_config is None:
        raise GuildError(
            "project '{}' has no 'sdd' config block: add one to sync SDD tasks".format(project), 1
        )
    patterns = _sdd_patterns(sdd_config)
    epic_files = sdd.discover_epic_files(sdd_config["root"], sdd_config["epics_dir"])
    failures = []
    for epic, path in epic_files:
        try:
            _sync_epic_file(ctx, project, epic, path, patterns)
        except GuildError as error:
            failures.append("{}: {}".format(path, error.message))
    return failures


def run(ctx, source):
    if source == "gh":
        return _sync_gh(ctx)
    if source == "sdd":
        return _sync_sdd(ctx)
    raise GuildError("sync source '{}' is not implemented in phase 1".format(source), 1)
