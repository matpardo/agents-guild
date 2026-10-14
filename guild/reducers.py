import json

from guild import merge_queue


def _party_started(conn, event):
    payload = event["payload"]
    conn.execute(
        "INSERT INTO parties (name, project, leader_session_id, generation, state)"
        " VALUES (?, ?, ?, 1, 'active')",
        (payload["party"], event["project"], event["session_id"]),
    )
    conn.execute(
        "INSERT INTO leaders (party, generation, session_id, session_name, started_at, ended_at)"
        " VALUES (?, 1, ?, ?, ?, NULL)",
        (payload["party"], event["session_id"], payload["session_name"], event["ts"]),
    )


def _party_resumed(conn, event):
    payload = event["payload"]
    conn.execute(
        "UPDATE leaders SET handoff_consumed_at = ? WHERE party = ? AND generation = ?"
        " AND handoff_consumed_at IS NULL",
        (event["ts"], payload["party"], payload["generation"] - 1),
    )
    conn.execute(
        "UPDATE leaders SET ended_at = ? WHERE party = ? AND generation = ? AND ended_at IS NULL",
        (event["ts"], payload["party"], payload["generation"] - 1),
    )
    conn.execute(
        "DELETE FROM leader_windows WHERE party = ? AND generation < ?",
        (payload["party"], payload["generation"]),
    )
    conn.execute(
        "UPDATE parties SET leader_session_id = ?, generation = ?, state = 'active' WHERE name = ?",
        (event["session_id"], payload["generation"], payload["party"]),
    )
    conn.execute(
        "INSERT INTO leaders (party, generation, session_id, session_name, started_at, ended_at)"
        " VALUES (?, ?, ?, ?, ?, NULL)",
        (
            payload["party"],
            payload["generation"],
            event["session_id"],
            payload["session_name"],
            event["ts"],
        ),
    )


def _party_closed(conn, event):
    payload = event["payload"]
    conn.execute("UPDATE parties SET state = 'closed' WHERE name = ?", (payload["party"],))
    conn.execute("UPDATE quests SET state = 'done' WHERE party = ? AND state = 'active'", (payload["party"],))
    conn.execute("UPDATE asks SET state = 'dismissed' WHERE party = ? AND state = 'open'", (payload["party"],))
    conn.execute("DELETE FROM claims WHERE party = ?", (payload["party"],))
    conn.execute("DELETE FROM raid_members WHERE party = ?", (payload["party"],))
    conn.execute("DELETE FROM leader_windows WHERE party = ?", (payload["party"],))
    conn.execute(
        "UPDATE leaders SET ended_at = ? WHERE party = ? AND generation = ? AND ended_at IS NULL",
        (event["ts"], payload["party"], payload["generation"]),
    )


def _party_handed_off(conn, event):
    payload = event["payload"]
    conn.execute("UPDATE parties SET state = 'awaiting-leader' WHERE name = ?", (payload["party"],))
    conn.execute(
        "UPDATE leaders SET handoff_path = ? WHERE party = ? AND generation = ?",
        (payload["handoff_path"], payload["party"], payload["generation"]),
    )


def _handoff_pruned(conn, event):
    payload = event["payload"]
    conn.execute(
        "UPDATE leaders SET handoff_path = NULL WHERE party = ? AND generation = ?",
        (payload["party"], payload["generation"]),
    )


def _leader_window_launched(conn, event):
    payload = event["payload"]
    conn.execute(
        "INSERT OR REPLACE INTO leader_windows (party, generation, window_id) VALUES (?, ?, ?)",
        (payload["party"], payload["generation"], payload["window_id"]),
    )


def _leader_located(conn, event):
    payload = event["payload"]
    conn.execute(
        "UPDATE leaders SET cwd = ?, permission_mode = ? WHERE party = ? AND generation = ?",
        (payload["cwd"], payload["permission_mode"], payload["party"], payload["generation"]),
    )


def _quest_done(conn, event):
    conn.execute("UPDATE quests SET state = 'done' WHERE slug = ?", (event["payload"]["slug"],))


def _quest_marked_incomplete(conn, event):
    return


def _quest_added(conn, event):
    payload = event["payload"]
    conn.execute(
        "INSERT INTO quests (slug, project, party, epic, title, state)"
        " VALUES (?, ?, ?, ?, ?, 'active')",
        (payload["slug"], payload["project"], payload["party"], payload["epic"], payload["title"]),
    )
    for task in payload["tasks"]:
        conn.execute(
            "INSERT INTO quest_tasks (quest, tid, title, state, summary, blocked_reason)"
            " VALUES (?, ?, ?, 'queued', NULL, NULL)",
            (payload["slug"], task["tid"], task["title"]),
        )


def _task_added(conn, event):
    payload = event["payload"]
    conn.execute(
        "INSERT INTO quest_tasks (quest, tid, title, state, summary, blocked_reason)"
        " VALUES (?, ?, ?, 'queued', NULL, NULL)",
        (payload["quest"], payload["tid"], payload["title"]),
    )


def _task_started(conn, event):
    payload = event["payload"]
    conn.execute(
        "UPDATE quest_tasks SET state = 'active', summary = ? WHERE quest = ? AND tid = ?",
        (payload["summary"], payload["quest"], payload["tid"]),
    )


def _task_blocked(conn, event):
    payload = event["payload"]
    conn.execute(
        "UPDATE quest_tasks SET state = 'blocked', blocked_reason = ? WHERE quest = ? AND tid = ?",
        (payload["reason"], payload["quest"], payload["tid"]),
    )


def _task_done(conn, event):
    payload = event["payload"]
    conn.execute(
        "UPDATE quest_tasks SET state = 'done', summary = ? WHERE quest = ? AND tid = ?",
        (payload["summary"], payload["quest"], payload["tid"]),
    )


def _epic_synced(conn, event):
    payload = event["payload"]
    project, epic = payload["project"], payload["epic"]
    conn.execute(
        "INSERT INTO epics (project, epic, title, jira_key, sdd_path, sdd_status)"
        " VALUES (?, ?, NULL, ?, ?, ?)"
        " ON CONFLICT(project, epic) DO UPDATE SET sdd_path = excluded.sdd_path,"
        " jira_key = excluded.jira_key, sdd_status = excluded.sdd_status",
        (project, epic, payload.get("jira_key"), payload["sdd_path"], payload.get("sdd_status")),
    )
    conn.execute("DELETE FROM tasks WHERE project = ? AND epic = ?", (project, epic))
    for task in payload["tasks"]:
        conn.execute(
            "INSERT INTO tasks (project, epic, tid, title, jira_key, deps, order_idx, sdd_status)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                project,
                epic,
                task["tid"],
                task["title"],
                task["jira_key"],
                _dump(task["deps"]),
                task["order_idx"],
                task["sdd_status"],
            ),
        )


def _tracker_synced(conn, event):
    payload = event["payload"]
    project = payload["project"]
    conn.execute("DELETE FROM cards WHERE project = ?", (project,))
    for card in payload["cards"]:
        conn.execute(
            "INSERT INTO cards (project, key, status, status_category, issue_type, parent_key)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (
                project,
                card["key"],
                card["status"],
                card["status_category"],
                card["issue_type"],
                card["parent_key"],
            ),
        )


_LEGACY_NEEDS_HUMAN_LIFECYCLE = "needs-human"
_PR_FLAG_FIELDS = ("needs_ask_answer", "needs_human_pr_review", "fixes_main", "fixes_flaky")


def _payload_flag(payload, field, fallback):
    if field in payload:
        return int(payload[field])
    return fallback


def _flags_and_lifecycle(payload, fallbacks):
    values = {field: _payload_flag(payload, field, fallbacks[field]) for field in _PR_FLAG_FIELDS}
    values["lifecycle"] = payload["lifecycle"]
    if payload["lifecycle"] == _LEGACY_NEEDS_HUMAN_LIFECYCLE:
        values["lifecycle"] = "draft"
        values["needs_ask_answer"] = 1
    return values


def _pr_tracked(conn, event):
    payload = event["payload"]
    values = _flags_and_lifecycle(payload, {field: 0 for field in _PR_FLAG_FIELDS})
    conn.execute(
        "INSERT INTO prs (repo, number, party, task_quest, task_tid, card, what, waits, lifecycle,"
        " branch, title, gh_state, gh_draft, checks_failing, checks_passing, seeded, synced_at,"
        " mergeable, review_comment_count, last_notified_comment_count, last_activity_at,"
        " needs_ask_answer, needs_human_pr_review, fixes_main, fixes_flaky)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, NULL, NULL, 0, 0, ?, ?, ?, ?, ?)",
        (
            payload["repo"],
            payload["number"],
            payload["party"],
            payload["task_quest"],
            payload["task_tid"],
            payload.get("card"),
            payload["what"],
            payload["waits"],
            values["lifecycle"],
            payload["branch"],
            payload["title"],
            payload["gh_state"],
            payload["gh_draft"],
            payload["seeded"],
            event["ts"],
            values["needs_ask_answer"],
            values["needs_human_pr_review"],
            values["fixes_main"],
            values["fixes_flaky"],
        ),
    )


def _pr_set(conn, event):
    payload = event["payload"]
    current = conn.execute(
        "SELECT lifecycle, waits, needs_ask_answer, needs_human_pr_review, last_activity_at,"
        " fixes_main, fixes_flaky, blocked_external FROM prs WHERE repo = ? AND number = ?",
        (payload["repo"], payload["number"]),
    ).fetchone()
    values = _flags_and_lifecycle(payload, current)
    blocked_external = payload.get("blocked_external", current["blocked_external"])
    changed = (
        current["waits"] != payload["waits"]
        or current["blocked_external"] != blocked_external
        or any(current[field] != values[field] for field in ("lifecycle",) + _PR_FLAG_FIELDS)
    )
    last_activity_at = event["ts"] if changed else current["last_activity_at"]
    conn.execute(
        "UPDATE prs SET lifecycle = ?, waits = ?, needs_ask_answer = ?, needs_human_pr_review = ?,"
        " fixes_main = ?, fixes_flaky = ?, blocked_external = ?, last_activity_at = ?"
        " WHERE repo = ? AND number = ?",
        (
            values["lifecycle"],
            payload["waits"],
            values["needs_ask_answer"],
            values["needs_human_pr_review"],
            values["fixes_main"],
            values["fixes_flaky"],
            blocked_external,
            last_activity_at,
            payload["repo"],
            payload["number"],
        ),
    )


_PR_SYNCED_CARRY_FORWARD_FIELDS = (
    "mergeable", "review_comment_count", "checks_pending", "review_decision", "merge_state", "base_branch",
    "unresolved_threads",
)


def _pr_synced_field(current, payload, field):
    if field in payload:
        return payload[field]
    return current[field]


def _pr_synced_changed(current, payload):
    fields = ("lifecycle", "gh_state", "gh_draft", "branch", "title", "checks_failing", "checks_passing")
    if any(current[field] != payload[field] for field in fields):
        return True
    return any(
        current[field] != _pr_synced_field(current, payload, field)
        for field in _PR_SYNCED_CARRY_FORWARD_FIELDS
    )


def _pr_synced(conn, event):
    payload = event["payload"]
    current = conn.execute(
        "SELECT lifecycle, gh_state, gh_draft, branch, title, checks_failing, checks_passing,"
        " checks_pending, mergeable, review_comment_count, review_decision, merge_state, base_branch,"
        " unresolved_threads, head_sha, last_activity_at FROM prs WHERE repo = ? AND number = ?",
        (payload["repo"], payload["number"]),
    ).fetchone()
    last_activity_at = event["ts"] if _pr_synced_changed(current, payload) else current["last_activity_at"]
    conn.execute(
        "UPDATE prs SET lifecycle = ?, gh_state = ?, gh_draft = ?, branch = ?, title = ?,"
        " checks_failing = ?, checks_passing = ?, checks_pending = ?, mergeable = ?, review_comment_count = ?,"
        " review_decision = ?, merge_state = ?, base_branch = ?, unresolved_threads = ?,"
        " head_sha = ?, synced_at = ?, last_activity_at = ?"
        " WHERE repo = ? AND number = ?",
        (
            payload["lifecycle"],
            payload["gh_state"],
            payload["gh_draft"],
            payload["branch"],
            payload["title"],
            payload["checks_failing"],
            payload["checks_passing"],
            _pr_synced_field(current, payload, "checks_pending"),
            _pr_synced_field(current, payload, "mergeable"),
            _pr_synced_field(current, payload, "review_comment_count"),
            _pr_synced_field(current, payload, "review_decision"),
            _pr_synced_field(current, payload, "merge_state"),
            _pr_synced_field(current, payload, "base_branch"),
            _pr_synced_field(current, payload, "unresolved_threads"),
            payload.get("head_sha") or current["head_sha"],
            payload["synced_at"],
            last_activity_at,
            payload["repo"],
            payload["number"],
        ),
    )
    _close_settled_fix_request(conn, payload["repo"], payload["number"])
    if "change_set" in payload:
        _store_change_set(conn, payload["repo"], payload["number"], payload["change_set"])


def _close_settled_fix_request(conn, repo, number):
    row = conn.execute(
        "SELECT lifecycle, checks_failing, mergeable, review_decision, unresolved_threads, merge_state"
        " FROM prs WHERE repo = ? AND number = ?",
        (repo, number),
    ).fetchone()
    if row["lifecycle"] not in ("merged", "closed") and merge_queue.fix_reasons(row):
        return
    conn.execute("UPDATE prs SET fix_requested_at = NULL WHERE repo = ? AND number = ?", (repo, number))


def _store_change_set(conn, repo, number, change_set):
    conn.execute(
        "UPDATE prs SET additions = ?, deletions = ?, created_at = ? WHERE repo = ? AND number = ?",
        (change_set["additions"], change_set["deletions"], change_set["created_at"], repo, number),
    )
    conn.execute("DELETE FROM pr_shared_areas WHERE repo = ? AND number = ?", (repo, number))
    for glob in change_set["globs"]:
        conn.execute(
            "INSERT INTO pr_shared_areas (repo, number, glob) VALUES (?, ?, ?)", (repo, number, glob)
        )
    if "paths" not in change_set:
        return
    conn.execute("DELETE FROM pr_files WHERE repo = ? AND number = ?", (repo, number))
    for path in change_set["paths"]:
        conn.execute("INSERT INTO pr_files (repo, number, path) VALUES (?, ?, ?)", (repo, number, path))


def _pr_fix_requested(conn, event):
    payload = event["payload"]
    conn.execute(
        "UPDATE prs SET fix_requested_at = ? WHERE repo = ? AND number = ?",
        (event["ts"], payload["repo"], payload["number"]),
    )


def _pr_comments_acknowledged(conn, event):
    payload = event["payload"]
    row = conn.execute(
        "SELECT review_comment_count FROM prs WHERE repo = ? AND number = ?",
        (payload["repo"], payload["number"]),
    ).fetchone()
    conn.execute(
        "UPDATE prs SET last_notified_comment_count = ? WHERE repo = ? AND number = ?",
        (row["review_comment_count"], payload["repo"], payload["number"]),
    )


def _snapshot_json(snapshot):
    if snapshot is None:
        return None
    return _dump(snapshot)


def _ask_created(conn, event):
    payload = event["payload"]
    conn.execute(
        "INSERT INTO asks (id, party, question, context, refs, options, state, answer, created_at,"
        " snapshot) VALUES (?, ?, ?, ?, ?, ?, 'open', NULL, ?, ?)",
        (
            payload["id"],
            payload["party"],
            payload["question"],
            payload["context"],
            _dump(payload["refs"]),
            _dump(payload["options"]),
            event["ts"],
            _snapshot_json(payload.get("snapshot")),
        ),
    )


def _ask_answered(conn, event):
    payload = event["payload"]
    conn.execute(
        "UPDATE asks SET state = 'answered', answer = ?, answered_at = ? WHERE id = ?",
        (payload["answer"], event["ts"], payload["id"]),
    )


def _ask_dismissed(conn, event):
    payload = event["payload"]
    conn.execute("UPDATE asks SET state = 'dismissed' WHERE id = ?", (payload["id"],))


def _notice_created(conn, event):
    payload = event["payload"]
    conn.execute(
        "INSERT INTO notices (id, party, scope, text, until_condition, expires_at, state, created_at,"
        " announces, unbound) VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)",
        (
            payload["id"],
            payload["party"],
            payload["scope"],
            payload["text"],
            payload["until_condition"],
            payload["expires_at"],
            event["ts"],
            payload.get("announces"),
            payload.get("unbound", False),
        ),
    )


def _notice_closed(conn, event):
    payload = event["payload"]
    conn.execute("UPDATE notices SET state = 'closed' WHERE id = ?", (payload["id"],))


def _notice_seen(conn, event):
    conn.execute("UPDATE notices SET seen_at = ? WHERE id = ?", (event["ts"], event["payload"]["id"]))


def _notice_unseen(conn, event):
    conn.execute("UPDATE notices SET seen_at = NULL WHERE id = ?", (event["payload"]["id"],))


def _claim_created(conn, event):
    payload = event["payload"]
    conn.execute(
        "INSERT OR REPLACE INTO claims (project, area, party, expires_at) VALUES (?, ?, ?, ?)",
        (payload["project"], payload["area"], payload["party"], payload["expires_at"]),
    )


def _claim_released(conn, event):
    payload = event["payload"]
    conn.execute(
        "DELETE FROM claims WHERE project = ? AND area = ?",
        (payload["project"], payload["area"]),
    )


def _raid_joined(conn, event):
    payload = event["payload"]
    conn.execute(
        "INSERT INTO raid_members (raid, party, expires_at, lead) VALUES (?, ?, ?, ?)"
        " ON CONFLICT(raid, party) DO UPDATE SET expires_at = excluded.expires_at, lead = excluded.lead",
        (payload["raid"], payload["party"], payload["expires_at"], 1 if payload.get("lead") else 0),
    )


def _raid_left(conn, event):
    payload = event["payload"]
    conn.execute(
        "DELETE FROM raid_members WHERE raid = ? AND party = ?",
        (payload["raid"], payload["party"]),
    )


def _raid_paused(conn, event):
    payload = event["payload"]
    conn.execute(
        "INSERT OR REPLACE INTO raid_pauses (raid, paused_at, paused_by) VALUES (?, ?, ?)",
        (payload["raid"], event["ts"], payload["party"]),
    )


def _raid_resumed(conn, event):
    conn.execute("DELETE FROM raid_pauses WHERE raid = ?", (event["payload"]["raid"],))


def _merge_queue_pinned(conn, event):
    payload = event["payload"]
    conn.execute(
        "INSERT OR REPLACE INTO merge_queue_pins"
        " (first_repo, first_number, second_repo, second_number, party, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (
            payload["first_repo"],
            payload["first_number"],
            payload["second_repo"],
            payload["second_number"],
            payload["author"],
            event["ts"],
        ),
    )


def _merge_queue_unpinned(conn, event):
    payload = event["payload"]
    conn.execute(
        "DELETE FROM merge_queue_pins WHERE first_repo = ? AND first_number = ?"
        " AND second_repo = ? AND second_number = ?",
        (payload["first_repo"], payload["first_number"], payload["second_repo"], payload["second_number"]),
    )


def _record_main_status(conn, event, source):
    payload = event["payload"]
    conn.execute(
        "INSERT OR REPLACE INTO main_status (repo, source, red, reason, external, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (payload["repo"], source, 1 if payload["red"] else 0, payload["reason"], payload.get("external"), event["ts"]),
    )


def _main_status_synced(conn, event):
    _record_main_status(conn, event, "gh")


def _main_marked(conn, event):
    _record_main_status(conn, event, "manual")


_WAIT_STATUS = {
    "permission": "waiting-permission",
    "elicitation": "waiting-input",
    "idle": "waiting-input",
}


def _set_session_status(conn, event, status, detail):
    conn.execute(
        "INSERT OR REPLACE INTO session_status (session_id, party, status, detail, since)"
        " VALUES (?, ?, ?, ?, ?)",
        (event["session_id"], event["party"], status, detail, event["ts"]),
    )


def _session_waiting(conn, event):
    payload = event["payload"]
    _set_session_status(conn, event, _WAIT_STATUS[payload["wait"]], payload["message"])


def _session_stopped(conn, event):
    _set_session_status(conn, event, "stopped", None)


def _session_working(conn, event):
    _set_session_status(conn, event, "working", None)


def _cost_sampled(conn, event):
    payload = event["payload"]
    conn.execute(
        "INSERT INTO cost_samples (session_id, day, model, party, quest, tid, input_tokens,"
        " cache_creation_tokens, cache_read_tokens, output_tokens) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        " ON CONFLICT (session_id, day, model, party, quest, tid) DO UPDATE SET"
        " input_tokens = input_tokens + excluded.input_tokens,"
        " cache_creation_tokens = cache_creation_tokens + excluded.cache_creation_tokens,"
        " cache_read_tokens = cache_read_tokens + excluded.cache_read_tokens,"
        " output_tokens = output_tokens + excluded.output_tokens",
        (
            event["session_id"],
            payload["day"],
            payload["model"],
            event["party"] or "",
            payload["quest"],
            payload["tid"],
            payload["input_tokens"],
            payload["cache_creation_tokens"],
            payload["cache_read_tokens"],
            payload["output_tokens"],
        ),
    )


def _lifecycle_ran(conn, event):
    return


def _resources_sampled(conn, event):
    payload = event["payload"]
    project = event["project"] or ""
    for category, item, size, state, flag, detail in payload["items"]:
        conn.execute(
            "INSERT OR REPLACE INTO resource_samples (project, ts, category, item, bytes, state, flag, detail)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (project, event["ts"], category, item, size, state, flag, detail),
        )
    machine = payload["machine"]
    docker = machine["docker"] or {}
    conn.execute(
        "INSERT OR REPLACE INTO resource_machine (ts, disk_total, disk_used, mem_total, mem_available,"
        " guild_db_bytes, docker_images, docker_images_reclaimable, docker_containers, docker_volumes,"
        " docker_build_cache) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            event["ts"],
            machine["disk_total"],
            machine["disk_used"],
            machine["mem_total"],
            machine["mem_available"],
            machine["guild_db_bytes"],
            docker.get("images"),
            docker.get("images_reclaimable"),
            docker.get("containers"),
            docker.get("volumes"),
            docker.get("build_cache"),
        ),
    )


def _dump(value):
    return json.dumps(value)


def _finding_recorded(conn, event):
    payload = event["payload"]
    conn.execute(
        "INSERT OR IGNORE INTO findings (project, class, repo, number, party, recorded_at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (payload["project"], payload["class"], payload["repo"], payload["number"], payload["party"], event["ts"]),
    )


_REDUCERS = {
    "party.started": _party_started,
    "party.resumed": _party_resumed,
    "party.closed": _party_closed,
    "party.handed_off": _party_handed_off,
    "handoff.pruned": _handoff_pruned,
    "leader.located": _leader_located,
    "leader.window_launched": _leader_window_launched,
    "quest.added": _quest_added,
    "quest.done": _quest_done,
    "quest.marked_incomplete": _quest_marked_incomplete,
    "task.added": _task_added,
    "task.started": _task_started,
    "task.blocked": _task_blocked,
    "task.done": _task_done,
    "epic.synced": _epic_synced,
    "tracker.synced": _tracker_synced,
    "finding.recorded": _finding_recorded,
    "pr.tracked": _pr_tracked,
    "pr.set": _pr_set,
    "pr.synced": _pr_synced,
    "pr.comments_acknowledged": _pr_comments_acknowledged,
    "pr.fix_requested": _pr_fix_requested,
    "ask.created": _ask_created,
    "ask.answered": _ask_answered,
    "ask.dismissed": _ask_dismissed,
    "notice.created": _notice_created,
    "notice.closed": _notice_closed,
    "notice.seen": _notice_seen,
    "notice.unseen": _notice_unseen,
    "claim.created": _claim_created,
    "claim.released": _claim_released,
    "raid.joined": _raid_joined,
    "raid.left": _raid_left,
    "raid.paused": _raid_paused,
    "raid.resumed": _raid_resumed,
    "merge_queue.pinned": _merge_queue_pinned,
    "merge_queue.unpinned": _merge_queue_unpinned,
    "main.status_synced": _main_status_synced,
    "main.marked": _main_marked,
    "session.waiting": _session_waiting,
    "session.stopped": _session_stopped,
    "session.working": _session_working,
    "cost.sampled": _cost_sampled,
    "lifecycle.ran": _lifecycle_ran,
    "resources.sampled": _resources_sampled,
}


def _retired(conn, event):
    return None


_REDUCERS.update(
    {kind: _retired for kind in ("dispatch.paused", "dispatch.resumed", "dispatch.decided", "dispatch.launched", "dispatch.launch_failed", "dispatch.bound")}
)


def apply(conn, event):
    _REDUCERS[event["kind"]](conn, event)
