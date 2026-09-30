import fnmatch
import json
from pathlib import Path

from guild import config, db, events, timeutil
from guild.adapters import github, jira_acli, sdd
from guild.commands import claim as claim_commands
from guild.commands import notice as notice_commands
from guild.commands import raid as raid_commands
from guild.errors import GuildError

_TRACKER_SUPPORTED_KINDS = ("jira-acli",)

_SDD_PATTERN_KEYS = ("task_heading", "key_ref", "deps_line", "status_line")
_SDD_OPTIONAL_PATTERN_KEYS = ("order_list", "key_line")

_FAILING_CONCLUSIONS = ("FAILURE", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED")
_SUCCESS_CONCLUSION = "SUCCESS"

_MERGED_GH_STATE = "MERGED"
_MERGE_NOTICE_TTL = "12h"
_MERGE_NOTICE_TEMPLATE = "{}#{} merged in main ({}/{}: {}). Parties with open branches: rebase."
_MERGE_NOTICE_SHARED_AREAS_SUFFIX = " Shared areas touched: {}"
_MERGE_NOTICE_RELEASED_SUFFIX = " Released: {}."
_AREA_PREFIX = "area:"


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


def _sync_pr(ctx, projects, row, failures):
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
    payload = {
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
    }
    change_set = _open_pr_change_set(ctx, projects, row, lifecycle, failures)
    if change_set is not None:
        payload["change_set"] = change_set
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
            payload,
        )
    return lifecycle


def _became_merged(row, lifecycle):
    return lifecycle == "merged" and row["gh_state"] != _MERGED_GH_STATE


def _project_for_repo(projects, repo):
    for project in projects:
        if repo in project["github"]["repos"]:
            return project
    return None


def _touched_shared_areas(shared_areas, changed_files):
    return [area for area in shared_areas if any(fnmatch.fnmatch(path, area) for path in changed_files)]


def _fetch_changed_files(ctx, row, failures):
    try:
        return github.pr_diff(ctx.cwd, row["repo"], row["number"])["paths"]
    except github.GhCommandError as error:
        failures.append(
            "{}#{}: shared areas check failed: {}".format(row["repo"], row["number"], error)
        )
        return None


def _queue_data_wanted(ctx, project, row):
    if raid_commands.member_raids(ctx.conn, ctx.now, row["party"]):
        return True
    return bool(claim_commands.held_areas(ctx, project["name"], row["party"]))


def _open_pr_change_set(ctx, projects, row, lifecycle, failures):
    if lifecycle in ("merged", "closed"):
        return None
    project = _project_for_repo(projects, row["repo"])
    if project is None or not project.get("shared_areas"):
        return None
    if not _queue_data_wanted(ctx, project, row):
        return None
    try:
        diff = github.pr_diff(ctx.cwd, row["repo"], row["number"])
    except github.GhCommandError as error:
        failures.append("{}#{}: merge queue data failed: {}".format(row["repo"], row["number"], error))
        return None
    return {
        "additions": diff["additions"],
        "deletions": diff["deletions"],
        "created_at": diff["created_at"],
        "globs": _touched_shared_areas(project["shared_areas"], diff["paths"]),
    }


def _shared_areas_line(touched):
    if not touched:
        return ""
    return _MERGE_NOTICE_SHARED_AREAS_SUFFIX.format(", ".join(touched))


def _released_line(released):
    if not released:
        return ""
    return _MERGE_NOTICE_RELEASED_SUFFIX.format(", ".join(released))


def _merge_notice_text(row, shared_line, released_line):
    base = _MERGE_NOTICE_TEMPLATE.format(
        row["repo"], row["number"], row["task_quest"], row["task_tid"], row["what"]
    )
    return base + shared_line + released_line


def _release_owned_claims(ctx, project, row, touched):
    held = set(claim_commands.held_areas(ctx, project["name"], row["party"]))
    released = []
    for glob in touched:
        area = "{}{}".format(_AREA_PREFIX, glob)
        if area not in held:
            continue
        claim_commands.release_for_party(ctx, project["name"], row["party"], area)
        released.append(glob)
    return released


def _post_merge_notice(ctx, row, raids, text):
    announces = "pr:{}#{}".format(row["repo"], row["number"])
    if notice_commands.announced(ctx.conn, announces):
        return
    for raid_row in raids:
        notice_commands.create_announcing(
            ctx, row["party"], text, "raid:{}".format(raid_row["raid"]), _MERGE_NOTICE_TTL, announces
        )


def _handle_merge(ctx, projects, row, failures):
    raids = raid_commands.member_raids(ctx.conn, ctx.now, row["party"])
    project = _project_for_repo(projects, row["repo"])
    shared_areas = project.get("shared_areas") if project is not None else None
    holds_areas = bool(shared_areas) and bool(
        claim_commands.held_areas(ctx, project["name"], row["party"])
    )
    touched = []
    released = []
    if shared_areas and (raids or holds_areas):
        changed_files = _fetch_changed_files(ctx, row, failures)
        if changed_files is not None:
            touched = _touched_shared_areas(shared_areas, changed_files)
            released = _release_owned_claims(ctx, project, row, touched)
    if not raids:
        return
    text = _merge_notice_text(row, _shared_areas_line(touched), _released_line(released))
    _post_merge_notice(ctx, row, raids, text)


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
    projects = config.load_all_projects(ctx.projects_dir)
    for row in rows:
        try:
            lifecycle = _sync_pr(ctx, projects, row, failures)
        except github.GhCommandError as error:
            failures.append("{}#{}: {}".format(row["repo"], row["number"], error))
            continue
        if _became_merged(row, lifecycle):
            _handle_merge(ctx, projects, row, failures)
    _close_met_notices(ctx)
    return failures


def _sdd_patterns(sdd_config):
    patterns = {key: sdd_config[key] for key in _SDD_PATTERN_KEYS}
    for optional_key in _SDD_OPTIONAL_PATTERN_KEYS:
        if optional_key in sdd_config:
            patterns[optional_key] = sdd_config[optional_key]
    return patterns


def _validate_sdd_source(sdd_config, project):
    has_root = "root" in sdd_config
    has_git_repo = "git_repo" in sdd_config
    has_git_ref = "git_ref" in sdd_config
    has_git = has_git_repo or has_git_ref
    if has_root and has_git:
        raise GuildError(
            "project '{}' sdd config must set either 'root' or 'git_repo'+'git_ref', not both".format(
                project
            ),
            1,
        )
    if not has_root and not has_git:
        raise GuildError(
            "project '{}' sdd config needs 'root', or both 'git_repo' and 'git_ref'".format(project), 1
        )
    if has_git and (not has_git_repo or not has_git_ref):
        raise GuildError(
            "project '{}' sdd config needs both 'git_repo' and 'git_ref'".format(project), 1
        )


def _root_epic_source(sdd_config):
    epics_path = Path(sdd_config["root"]).expanduser() / sdd_config["epics_dir"]
    if not epics_path.is_dir():
        raise GuildError("sdd epics directory {} does not exist: check sdd.root".format(epics_path), 1)
    for epic, path in sdd.discover_epic_files(sdd_config["root"], sdd_config["epics_dir"]):
        yield epic, path.read_text(), str(path)


def _git_epic_source(sdd_config):
    repo = sdd_config["git_repo"]
    ref = sdd_config["git_ref"]
    epics_dir = sdd_config["epics_dir"]
    try:
        sdd.git_fetch(repo)
    except sdd.GitSddError as error:
        raise GuildError("git fetch failed for {}: {}".format(repo, error), 1)
    try:
        files = sdd.git_tasks_files(repo, ref, epics_dir)
    except sdd.GitSddError as error:
        raise GuildError("git ls-tree failed for {} at {}: {}".format(repo, ref, error), 1)
    if not files:
        raise GuildError(
            "no tasks.md files found under {} at {}:{}: check sdd.git_ref".format(repo, ref, epics_dir),
            1,
        )
    for epic, path in files:
        try:
            text = sdd.git_show(repo, ref, path)
        except sdd.GitSddError as error:
            raise GuildError("git show failed for {}:{}: {}".format(ref, path, error), 1)
        yield epic, text, "git:{}:{}".format(ref, path)


def _sync_epic_file(ctx, project, epic, text, sdd_path, patterns, epic_key_field, epic_status_field):
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
                "sdd_path": sdd_path,
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
    _validate_sdd_source(sdd_config, project)
    patterns = _sdd_patterns(sdd_config)
    epic_key_field = sdd_config.get("epic_key_field")
    epic_status_field = sdd_config.get("epic_status_field")
    epic_source = _root_epic_source(sdd_config) if "root" in sdd_config else _git_epic_source(sdd_config)
    failures = []
    for epic, text, sdd_path in epic_source:
        try:
            _sync_epic_file(ctx, project, epic, text, sdd_path, patterns, epic_key_field, epic_status_field)
        except GuildError as error:
            failures.append("{}: {}".format(sdd_path, error.message))
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
