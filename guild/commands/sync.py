import fnmatch
import json
import re
import sqlite3
from pathlib import Path

from guild import config, db, events, handoff_prune, human_ready, localbase, paths, timeutil, trace_validator
from guild.adapters import github, jira_acli, sdd
from guild.commands import claim as claim_commands
from guild.commands import drift as drift_commands
from guild.commands import lifecycle as lifecycle_commands
from guild.commands import notice as notice_commands
from guild.commands import raid as raid_commands
from guild.errors import GuildError

_SDD_PATTERN_KEYS = ("task_heading", "key_ref", "deps_line", "status_line")
_SDD_OPTIONAL_PATTERN_KEYS = ("order_list", "key_line")

_FAILING_CONCLUSIONS = ("FAILURE", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED")
_SUCCESS_CONCLUSION = "SUCCESS"
_CHECK_RUN_COMPLETED_STATUS = "COMPLETED"
_STATUS_CONTEXT_TYPENAME = "StatusContext"
_STATUS_CONTEXT_PENDING_STATES = ("PENDING", "EXPECTED")
_STATUS_CONTEXT_FAILING_STATES = ("FAILURE", "ERROR")
_STATUS_CONTEXT_SUCCESS_STATE = "SUCCESS"

_DRAFT_SUB_LIFECYCLES = ("converging",)

_MERGED_GH_STATE = "MERGED"
_CLOSED_GH_STATE = "CLOSED"
_MERGE_NOTICE_TTL = "12h"
_MERGE_NOTICE_TEMPLATE = "{}#{} merged in main ({}). Parties with open branches: rebase."
_MERGE_NOTICE_SHARED_AREAS_SUFFIX = " Shared areas touched: {}"
_MERGE_NOTICE_RELEASED_SUFFIX = " Released: {}."
_MERGE_NOTICE_MOVES_SUFFIX = " Owner follow-up: {}."
_AREA_PREFIX = "area:"

_FAST_FORWARD_NOTICE_TTL = "12h"
_FAST_FORWARD_NOTICE_TEMPLATE = "local {} of {} {} commits behind origin, not updated: {}"

_MIGRATION_NOTICE_TTL = "12h"
_MIGRATION_NOTICE_TEMPLATE = (
    "Migration version {} is claimed by more than one open PR: {}. Renumber before merging."
)
_MIGRATION_VERSION_PATTERN = re.compile(r"^(\d+)")


def _classify_status_context(entry):
    state = entry.get("state")
    if state in _STATUS_CONTEXT_PENDING_STATES:
        return "pending"
    if state == _STATUS_CONTEXT_SUCCESS_STATE:
        return "passing"
    if state in _STATUS_CONTEXT_FAILING_STATES:
        return "failing"
    return None


def _classify_check_run(entry):
    status = entry.get("status")
    if status is not None and status != _CHECK_RUN_COMPLETED_STATUS:
        return "pending"
    conclusion = entry.get("conclusion")
    if conclusion == _SUCCESS_CONCLUSION:
        return "passing"
    if conclusion in _FAILING_CONCLUSIONS:
        return "failing"
    return None


def _classify_check(entry):
    if entry.get("__typename") == _STATUS_CONTEXT_TYPENAME:
        return _classify_status_context(entry)
    return _classify_check_run(entry)


def _count_checks(rollup):
    counts = {"failing": 0, "passing": 0, "pending": 0}
    for entry in rollup or []:
        kind = _classify_check(entry)
        if kind is not None:
            counts[kind] += 1
    return counts["failing"], counts["passing"], counts["pending"]


def _lifecycle_from_gh(current_lifecycle, gh_data):
    if gh_data.get("mergedAt"):
        return "merged"
    if gh_data.get("state") == "CLOSED":
        return "closed"
    is_draft = gh_data.get("isDraft")
    if is_draft is None:
        return current_lifecycle
    if not is_draft:
        return "ready"
    if current_lifecycle in _DRAFT_SUB_LIFECYCLES:
        return current_lifecycle
    return "draft"


_UNKNOWN_MERGE_STATE = "UNKNOWN"


def _open_pr_unresolved_threads(ctx, row, lifecycle, failures):
    if lifecycle in ("merged", "closed"):
        return None
    try:
        return github.unresolved_thread_count(ctx.cwd, row["repo"], row["number"])
    except github.GhCommandError as error:
        failures.append("{}#{}: review threads check failed: {}".format(row["repo"], row["number"], error))
        return None


def _pr_checks_billing(ctx, row, head_sha, failing, failures):
    if failing == 0:
        return None
    if not head_sha:
        return 0
    try:
        checks = github.branch_checks(ctx.cwd, row["repo"], head_sha)
        failing_runs = [check for check in checks if check["conclusion"] in _FAILING_CONCLUSIONS]
        return int(len(failing_runs) == failing and _billing_blocked(ctx, row["repo"], checks))
    except github.GhCommandError as error:
        failures.append("{}#{}: billing check failed: {}".format(row["repo"], row["number"], error))
        return 0


def _trace_facts(project, row, gh_data, lifecycle, runner):
    if project is None or "trace_validator" not in project.get("human_ready", {}) or lifecycle != "ready":
        return None, None
    cwd = lifecycle_commands.checkout_for(project, row["repo"])
    if cwd is None:
        return None, "no local clone of {}".format(row["repo"])
    discussion = {"comments": gh_data.get("comments") or [], "reviews": gh_data.get("reviews") or []}
    return trace_validator.check(project, cwd, row["number"], gh_data.get("headRefOid"), discussion, runner)


def _sync_pr(ctx, projects, row, failures, lifecycle_runner):
    gh_data = github.pr_view(
        ctx.cwd,
        row["repo"],
        row["number"],
        [
            "state", "isDraft", "mergedAt", "headRefName", "title", "statusCheckRollup",
            "reviewDecision", "mergeable", "mergeStateStatus", "baseRefName", "comments", "reviews", "headRefOid",
            "isCrossRepository", "commits", "labels", "author",
        ],
    )
    failing, passing, pending = _count_checks(gh_data.get("statusCheckRollup"))
    lifecycle = _lifecycle_from_gh(row["lifecycle"], gh_data)
    review_comment_count = len(gh_data.get("comments") or []) + len(gh_data.get("reviews") or [])
    head_date = human_ready.head_commit_date(gh_data.get("commits") or [], gh_data.get("headRefOid"))
    project = _project_for_repo(projects, row["repo"])
    trace_valid, trace_reason = _trace_facts(project, row, gh_data, lifecycle, lifecycle_runner)
    payload = {
        "repo": row["repo"],
        "number": row["number"],
        "trace_valid": trace_valid,
        "trace_reason": trace_reason,
        "comments_after_head": human_ready.comments_after_head(
            head_date,
            (gh_data.get("author") or {}).get("login"),
            gh_data.get("comments") or [],
            gh_data.get("reviews") or [],
        ),
        "other_author_comments": human_ready.other_author_comments(
            (gh_data.get("author") or {}).get("login"),
            gh_data.get("comments") or [],
            gh_data.get("reviews") or [],
            ((project or {}).get("human_ready") or {}).get("notice_comments", []),
        ),
        "ci_label": human_ready.ci_label_flag(project, gh_data.get("labels") or []),
        "gh_state": gh_data.get("state"),
        "gh_draft": gh_data.get("isDraft"),
        "branch": gh_data.get("headRefName"),
        "head_sha": gh_data.get("headRefOid"),
        "cross_repository": gh_data.get("isCrossRepository"),
        "title": gh_data.get("title"),
        "checks_failing": failing,
        "checks_billing": _pr_checks_billing(ctx, row, gh_data.get("headRefOid"), failing, failures),
        "checks_passing": passing,
        "checks_pending": pending,
        "lifecycle": lifecycle,
        "mergeable": gh_data.get("mergeable"),
        "review_decision": gh_data.get("reviewDecision"),
        "base_branch": gh_data.get("baseRefName"),
        "review_comment_count": review_comment_count,
        "synced_at": timeutil.to_iso(ctx.now),
    }
    merge_state = gh_data.get("mergeStateStatus")
    if merge_state not in (None, _UNKNOWN_MERGE_STATE):
        payload["merge_state"] = merge_state
    unresolved_threads = _open_pr_unresolved_threads(ctx, row, lifecycle, failures)
    if unresolved_threads is not None:
        payload["unresolved_threads"] = unresolved_threads
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


def _became_closed(row, lifecycle):
    return lifecycle == "closed" and row["gh_state"] != _CLOSED_GH_STATE


def _lifecycle_trigger(row, lifecycle):
    if row["seeded"] == 1:
        return None
    if _became_merged(row, lifecycle):
        return ("on_pr_merged", row["repo"], row["number"])
    if _became_closed(row, lifecycle):
        return ("on_pr_closed", row["repo"], row["number"])
    return None


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
    if project is None:
        return None
    tracks_files = bool(project.get("max_open_prs_per_file"))
    tracks_globs = bool(project.get("shared_areas")) and _queue_data_wanted(ctx, project, row)
    if not tracks_files and not tracks_globs:
        return None
    try:
        diff = github.pr_diff(ctx.cwd, row["repo"], row["number"])
    except github.GhCommandError as error:
        failures.append("{}#{}: merge queue data failed: {}".format(row["repo"], row["number"], error))
        return None
    change_set = {
        "additions": diff["additions"],
        "deletions": diff["deletions"],
        "created_at": diff["created_at"],
        "globs": _touched_shared_areas(project["shared_areas"], diff["paths"]) if tracks_globs else [],
    }
    if tracks_files:
        change_set["paths"] = diff["paths"]
    return change_set


def _shared_areas_line(touched):
    if not touched:
        return ""
    return _MERGE_NOTICE_SHARED_AREAS_SUFFIX.format(", ".join(touched))


def _released_line(released):
    if not released:
        return ""
    return _MERGE_NOTICE_RELEASED_SUFFIX.format(", ".join(released))


def _moves_line(moves):
    if not moves:
        return ""
    return _MERGE_NOTICE_MOVES_SUFFIX.format("; ".join(moves))


def _merge_notice_label(row):
    if row["task_quest"] is not None:
        return "{}/{}: {}".format(row["task_quest"], row["task_tid"], row["what"])
    if row["card"] is not None:
        return "{}: {}".format(row["card"], row["what"])
    return row["what"]


def _merge_notice_text(row, shared_line, released_line, moves_line):
    base = _MERGE_NOTICE_TEMPLATE.format(row["repo"], row["number"], _merge_notice_label(row))
    return base + shared_line + released_line + moves_line


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
    moves_line = _moves_line(drift_commands.merged_pr_moves(ctx.conn, row))
    text = _merge_notice_text(row, _shared_areas_line(touched), _released_line(released), moves_line)
    _post_merge_notice(ctx, row, raids, text)


def _post_fast_forward_notice(ctx, project, clone, base, outcome):
    tip = localbase.origin_tip(clone["path"], base)
    announces = "ffbase:{}:{}:{}".format(project["name"], clone["repo"], tip)
    if notice_commands.announced(ctx.conn, announces):
        return
    text = _FAST_FORWARD_NOTICE_TEMPLATE.format(
        base, clone["repo"], outcome["behind"], outcome["reason"]
    )
    notice_commands.create_announcing(
        ctx, None, text, "project:{}".format(project["name"]), _FAST_FORWARD_NOTICE_TTL, announces
    )


def _fast_forward_clone_mutating_git(ctx, project, clone):
    base = localbase.base_branch(clone["path"])
    if base is None:
        return
    outcome = localbase.fast_forward_base_mutating_git(clone["path"], base)
    if outcome["reason"] is None:
        return
    _post_fast_forward_notice(ctx, project, clone, base, outcome)


def _fast_forward_merged_bases_mutating_git(ctx, projects, merged_repos):
    for project in projects:
        if not project.get("fast_forward_base"):
            continue
        for clone in localbase.locate_clones(project):
            if clone["repo"] in merged_repos:
                _fast_forward_clone_mutating_git(ctx, project, clone)


def _migration_versions(migration_paths, changed_files):
    versions = set()
    for path in changed_files:
        if not any(fnmatch.fnmatch(path, pattern) for pattern in migration_paths):
            continue
        match = _MIGRATION_VERSION_PATTERN.match(path.rsplit("/", 1)[-1])
        if match:
            versions.add(match.group(1))
    return versions


def _versions_by_pr(ctx, project, rows, failures):
    by_pr = {}
    for row in rows:
        if row["repo"] not in project["github"]["repos"]:
            continue
        try:
            paths = github.pr_diff(ctx.cwd, row["repo"], row["number"])["paths"]
        except github.GhCommandError as error:
            failures.append(
                "{}#{}: migration clash check failed: {}".format(row["repo"], row["number"], error)
            )
            continue
        by_pr[(row["repo"], row["number"])] = (row, _migration_versions(project["migration_paths"], paths))
    return by_pr


def _post_migration_notices(ctx, project, version, clashing):
    refs = ", ".join("{}#{}".format(row["repo"], row["number"]) for row in clashing)
    text = _MIGRATION_NOTICE_TEMPLATE.format(version, refs)
    for row in clashing:
        announces = "migration:{}:{}:{}#{}".format(project["name"], version, row["repo"], row["number"])
        if notice_commands.announced(ctx.conn, announces):
            continue
        for raid_row in raid_commands.member_raids(ctx.conn, ctx.now, row["party"]):
            notice_commands.create_announcing(
                ctx,
                row["party"],
                text,
                "raid:{}".format(raid_row["raid"]),
                _MIGRATION_NOTICE_TTL,
                announces,
            )


def _check_migration_clashes(ctx, projects, failures):
    open_rows = ctx.conn.execute(
        "SELECT * FROM prs WHERE lifecycle NOT IN ('merged', 'closed') ORDER BY repo, number"
    ).fetchall()
    for project in projects:
        if not project.get("migration_paths"):
            continue
        by_pr = _versions_by_pr(ctx, project, open_rows, failures)
        owners_by_version = {}
        for row, versions in by_pr.values():
            for version in versions:
                owners_by_version.setdefault(version, []).append(row)
        for version in sorted(owners_by_version):
            clashing = owners_by_version[version]
            if len(clashing) < 2:
                continue
            _post_migration_notices(ctx, project, version, clashing)


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


_BILLING_EXTERNAL = "billing"
_BILLING_FAILURE_TEXT = "recent account payments have failed"


def _branch_red_reason(checks):
    failing = [check["name"] for check in checks if check["conclusion"] in _FAILING_CONCLUSIONS]
    if not failing:
        return None
    return "checks failing: {}".format(", ".join(sorted(failing)))


def _billing_blocked(ctx, repo, checks):
    failing = [check for check in checks if check["conclusion"] in _FAILING_CONCLUSIONS]
    for check in failing:
        if check["annotations_count"] == 0:
            return False
        messages = github.check_run_annotation_messages(ctx.cwd, repo, check["id"])
        if not any(_BILLING_FAILURE_TEXT in message.lower() for message in messages):
            return False
    return bool(failing)


def _recorded_gh_status(ctx, repo):
    row = ctx.conn.execute(
        "SELECT red, reason, external FROM main_status WHERE repo = ? AND source = 'gh'", (repo,)
    ).fetchone()
    if row is None:
        return False, None, None
    return bool(row["red"]), row["reason"], row["external"]


def _record_main_status(ctx, project, repo, reason, external):
    with db.writing(ctx.conn):
        events.record(
            ctx.conn,
            ctx.now,
            ctx.origin,
            None,
            ctx.session_id,
            project["name"],
            "main.status_synced",
            "guild",
            {"repo": repo, "red": reason is not None, "reason": reason, "external": external},
        )


def _sync_repo_main_status(ctx, project, repo, base, failures):
    try:
        checks = github.branch_checks(ctx.cwd, repo, base)
        external = _BILLING_EXTERNAL if _billing_blocked(ctx, repo, checks) else None
    except github.GhCommandError as error:
        failures.append("{}: main status check failed: {}".format(repo, error))
        return
    reason = _branch_red_reason(checks)
    if _recorded_gh_status(ctx, repo) == (reason is not None, reason, external):
        return
    _record_main_status(ctx, project, repo, reason, external)


def _sync_main_status(ctx, projects, failures):
    for project in projects:
        for clone in localbase.locate_clones(project):
            base = localbase.base_branch(clone["path"])
            if base is None:
                continue
            _sync_repo_main_status(ctx, project, clone["repo"], base, failures)


def _prune_handoffs(ctx, failures):
    try:
        handoff_prune.prune(ctx, paths.handoffs_dir())
    except (GuildError, OSError, sqlite3.Error) as error:
        failures.append("handoff prune failed: {}".format(error))


def _sync_gh(ctx, lifecycle_runner):
    rows = ctx.conn.execute(
        "SELECT * FROM prs WHERE lifecycle NOT IN ('merged', 'closed')"
    ).fetchall()
    failures = []
    projects = config.load_all_projects(ctx.projects_dir)
    merged_repos = set()
    triggers = []
    for row in rows:
        try:
            lifecycle = _sync_pr(ctx, projects, row, failures, lifecycle_runner)
        except github.GhCommandError as error:
            failures.append("{}#{}: {}".format(row["repo"], row["number"], error))
            continue
        if _became_merged(row, lifecycle):
            _handle_merge(ctx, projects, row, failures)
            merged_repos.add(row["repo"])
        trigger = _lifecycle_trigger(row, lifecycle)
        if trigger is not None:
            triggers.append(trigger)
    _fast_forward_merged_bases_mutating_git(ctx, projects, merged_repos)
    _check_migration_clashes(ctx, projects, failures)
    _sync_main_status(ctx, projects, failures)
    _close_met_notices(ctx)
    lifecycle_commands.run_sync_triggers(ctx, projects, triggers, lifecycle_runner)
    _prune_handoffs(ctx, failures)
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


def sync_sdd(ctx, project):
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
    if project_data.get("tracker") is None:
        raise GuildError(
            "project '{}' has no 'tracker' config block: add one to sync tracker cards".format(
                project
            ),
            1,
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


def _sync_tracker(ctx, project):
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


_PROJECT_SOURCES = {"sdd": ("sdd", sync_sdd), "tracker": ("tracker", _sync_tracker)}


def _sync_all_projects(ctx, source):
    config_key, sync_project = _PROJECT_SOURCES[source]
    failures = []
    for project in config.load_all_projects(ctx.projects_dir):
        if config_key not in project:
            continue
        try:
            failures.extend(
                "{}: {}".format(project["name"], failure) for failure in sync_project(ctx, project["name"])
            )
        except GuildError as error:
            failures.append("{}: {}".format(project["name"], error.message))
    return failures


def run(ctx, source, all_projects, lifecycle_runner):
    if source == "gh":
        if all_projects:
            raise GuildError("--all-projects applies to sdd and tracker sources only", 1)
        return _sync_gh(ctx, lifecycle_runner)
    if source not in _PROJECT_SOURCES:
        raise GuildError("sync source '{}' is not implemented".format(source), 1)
    if all_projects:
        return _sync_all_projects(ctx, source)
    _, sync_project = _PROJECT_SOURCES[source]
    return sync_project(ctx, config.require_project(ctx.cwd, ctx.projects_dir))
