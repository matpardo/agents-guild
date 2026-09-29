import json

from guild import config, db, events, timeutil
from guild.adapters import github, jira_acli, sdd
from guild.commands import notice as notice_commands
from guild.errors import GuildError

_TRACKER_SUPPORTED_KINDS = ("jira-acli",)

_SDD_PATTERN_KEYS = ("task_heading", "key_ref", "deps_line", "status_line")
_SDD_OPTIONAL_PATTERN_KEYS = ("order_list", "key_line")

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
    for optional_key in _SDD_OPTIONAL_PATTERN_KEYS:
        if optional_key in sdd_config:
            patterns[optional_key] = sdd_config[optional_key]
    return patterns


def _sync_epic_file(ctx, project, epic, path, patterns, epic_key_field, epic_status_field):
    text = path.read_text()
    tasks = sdd.parse_tasks_text(text, patterns)
    if tasks is None:
        raise GuildError("no matching task headings", 1)
    jira_key = sdd.parse_epic_key(text, epic_key_field)
    sdd_status = sdd.parse_epic_status(text, epic_status_field)
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
            {
                "project": project,
                "epic": epic,
                "sdd_path": str(path),
                "jira_key": jira_key,
                "sdd_status": sdd_status,
                "tasks": tasks,
            },
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
    epic_key_field = sdd_config.get("epic_key_field")
    epic_status_field = sdd_config.get("epic_status_field")
    epic_files = sdd.discover_epic_files(sdd_config["root"], sdd_config["epics_dir"])
    failures = []
    for epic, path in epic_files:
        try:
            _sync_epic_file(ctx, project, epic, path, patterns, epic_key_field, epic_status_field)
        except GuildError as error:
            failures.append("{}: {}".format(path, error.message))
    return failures


def _require_tracker_config(project_data, project):
    tracker_config = project_data.get("tracker")
    if tracker_config is None:
        raise GuildError(
            "project '{}' has no 'tracker' config block: add one to sync tracker cards".format(
                project
            ),
            1,
        )
    kind = tracker_config.get("kind")
    if kind not in _TRACKER_SUPPORTED_KINDS:
        raise GuildError(
            "project '{}' tracker.kind '{}' is not supported".format(project, kind), 1
        )


def _distinct_keys(conn, table, project):
    rows = conn.execute(
        "SELECT DISTINCT jira_key FROM {} WHERE project = ? AND jira_key IS NOT NULL".format(
            table
        ),
        (project,),
    ).fetchall()
    return [row["jira_key"] for row in rows]


def _sync_children(cards, failures, query_errors, epic_key):
    try:
        children, invalid_keys = jira_acli.children_of(epic_key)
    except jira_acli.JiraAcliError as error:
        query_errors.append("{}: {}".format(epic_key, error))
        return
    for key in invalid_keys:
        failures.append("{}: invalid tracker key".format(key))
    for card in children:
        card["parent_key"] = epic_key
        cards[card["key"]] = card


def _sync_by_key(cards, failures, query_errors, keys):
    if not keys:
        return
    try:
        found_cards, invalid_keys = jira_acli.cards_by_key(keys)
    except jira_acli.JiraAcliError as error:
        query_errors.append("tracker query failed: {}".format(error))
        return
    for key in invalid_keys:
        failures.append("{}: invalid tracker key".format(key))
    found_keys = set()
    for card in found_cards:
        found_keys.add(card["key"])
        card["parent_key"] = None
        cards[card["key"]] = card
    invalid_keys_set = set(invalid_keys)
    for key in keys:
        if key in found_keys or key in invalid_keys_set:
            continue
        failures.append("{}: not found in tracker".format(key))


def _missing_keys(keys, seen):
    result = []
    for key in keys:
        if key in seen or key in result:
            continue
        result.append(key)
    return result


_SNAPSHOT_KEPT = "tracker snapshot not updated: previous cards kept"


def _sync_tracker(ctx):
    project = config.require_project(ctx.cwd, ctx.projects_dir)
    project_data = config.load_project(ctx.projects_dir, project)
    _require_tracker_config(project_data, project)

    epic_keys = _distinct_keys(ctx.conn, "epics", project)
    task_keys = _distinct_keys(ctx.conn, "tasks", project)

    failures = []
    query_errors = []
    cards = {}
    for epic_key in epic_keys:
        _sync_children(cards, failures, query_errors, epic_key)
    if query_errors:
        return failures + query_errors + [_SNAPSHOT_KEPT]

    remaining_keys = _missing_keys(epic_keys + task_keys, set(cards))
    _sync_by_key(cards, failures, query_errors, remaining_keys)
    if query_errors:
        return failures + query_errors + [_SNAPSHOT_KEPT]

    with db.writing(ctx.conn):
        events.record(
            ctx.conn,
            ctx.now,
            ctx.origin,
            None,
            ctx.session_id,
            project,
            "tracker.synced",
            "local",
            {"project": project, "cards": list(cards.values())},
        )
    return failures


def run(ctx, source):
    if source == "gh":
        return _sync_gh(ctx)
    if source == "sdd":
        return _sync_sdd(ctx)
    if source == "tracker":
        return _sync_tracker(ctx)
    raise GuildError("sync source '{}' is not implemented".format(source), 1)
