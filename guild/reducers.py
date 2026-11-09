import json

from guild import solo_players
from guild.errors import GuildError


def _party_started(conn, event):
    payload = event["payload"]
    conn.execute(
        "INSERT INTO parties (name, project, leader_session_id, generation, state, reason, from_adventurer,"
        " updated_at) VALUES (?, ?, ?, 1, 'active', ?, ?, ?)",
        (
            payload["party"],
            event["project"],
            event["session_id"],
            payload.get("reason"),
            payload.get("from_adventurer"),
            event["ts"],
        ),
    )
    conn.execute(
        "INSERT INTO leaders (party, generation, session_id, session_name, started_at, ended_at)"
        " VALUES (?, 1, ?, ?, ?, NULL)",
        (payload["party"], event["session_id"], payload["session_name"], event["ts"]),
    )


def _party_resumed(conn, event):
    payload = event["payload"]
    conn.execute(
        "UPDATE leaders SET handoff_consumed_at = ? WHERE party = ? AND generation = ? AND handoff_consumed_at IS NULL",
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
        "UPDATE parties SET leader_session_id = ?, generation = ?, state = 'active', parked = NULL, parked_at = NULL,"
        " updated_at = ? WHERE name = ?",
        (event["session_id"], payload["generation"], event["ts"], payload["party"]),
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
    conn.execute("UPDATE parties SET state = 'closed', updated_at = ? WHERE name = ?", (event["ts"], payload["party"]))
    conn.execute(
        "UPDATE quests SET state = 'done', updated_at = ? WHERE party = ? AND state = 'active'",
        (event["ts"], payload["party"]),
    )
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
    conn.execute(
        "UPDATE parties SET state = 'awaiting-leader', updated_at = ? WHERE name = ?", (event["ts"], payload["party"])
    )
    conn.execute(
        "UPDATE leaders SET handoff_path = ? WHERE party = ? AND generation = ?",
        (payload["handoff_path"], payload["party"], payload["generation"]),
    )
    if payload.get("parked") is not None:
        _set_parked(conn, event["ts"], payload["party"], payload["parked"])


def _set_parked(conn, ts, party, reason):
    conn.execute("UPDATE parties SET parked = ?, parked_at = ?, updated_at = ? WHERE name = ?", (reason, ts, ts, party))


def _party_parked(conn, event):
    _set_parked(conn, event["ts"], event["payload"]["party"], event["payload"]["reason"])


def _party_unparked(conn, event):
    conn.execute(
        "UPDATE parties SET parked = NULL, parked_at = NULL, updated_at = ? WHERE name = ?",
        (event["ts"], event["payload"]["party"]),
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


def _health_window_launched(conn, event):
    conn.execute(
        "INSERT OR REPLACE INTO health_windows (window_id, project) VALUES (?, ?)",
        (event["payload"]["window_id"], event["project"]),
    )


def _leader_located(conn, event):
    payload = event["payload"]
    conn.execute(
        "UPDATE leaders SET cwd = ?, permission_mode = ? WHERE party = ? AND generation = ?",
        (payload["cwd"], payload["permission_mode"], payload["party"], payload["generation"]),
    )


def _quest_done(conn, event):
    conn.execute(
        "UPDATE quests SET state = 'done', updated_at = ? WHERE slug = ?", (event["ts"], event["payload"]["slug"])
    )


def _quest_marked_incomplete(conn, event):
    return


def _quest_added(conn, event):
    payload = event["payload"]
    conn.execute(
        "INSERT INTO quests (slug, project, party, epic, title, state, created_at, updated_at, left_by)"
        " VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?)",
        (
            payload["slug"],
            payload["project"],
            payload["party"],
            payload["epic"],
            payload["title"],
            event["ts"],
            event["ts"],
            payload.get("left_by"),
        ),
    )
    for task in payload["tasks"]:
        conn.execute(
            "INSERT INTO quest_tasks (quest, tid, title, state, summary, blocked_reason, created_at, updated_at)"
            " VALUES (?, ?, ?, 'queued', NULL, NULL, ?, ?)",
            (payload["slug"], task["tid"], task["title"], event["ts"], event["ts"]),
        )


def _quest_taken(conn, event):
    payload = event["payload"]
    conn.execute(
        "UPDATE quests SET party = ?, updated_at = ? WHERE slug = ?", (payload["party"], event["ts"], payload["slug"])
    )


def _quest_released(conn, event):
    payload = event["payload"]
    conn.execute(
        "UPDATE quests SET party = NULL, left_by = ?, updated_at = ? WHERE slug = ?",
        (payload["party"], event["ts"], payload["slug"]),
    )


def _task_added(conn, event):
    payload = event["payload"]
    conn.execute(
        "INSERT INTO quest_tasks (quest, tid, title, state, summary, blocked_reason, created_at, updated_at, no_sdd)"
        " VALUES (?, ?, ?, 'queued', NULL, NULL, ?, ?, ?)",
        (
            payload["quest"],
            payload["tid"],
            payload["title"],
            event["ts"],
            event["ts"],
            int(payload.get("no_sdd", False)),
        ),
    )
    conn.execute("UPDATE quests SET updated_at = ? WHERE slug = ?", (event["ts"], payload["quest"]))


def _task_started(conn, event):
    payload = event["payload"]
    conn.execute(
        "UPDATE quest_tasks SET state = 'active', summary = ?, updated_at = ? WHERE quest = ? AND tid = ?",
        (payload["summary"], event["ts"], payload["quest"], payload["tid"]),
    )


def _task_blocked(conn, event):
    payload = event["payload"]
    conn.execute(
        "UPDATE quest_tasks SET state = 'blocked', blocked_reason = ?, updated_at = ? WHERE quest = ? AND tid = ?",
        (payload["reason"], event["ts"], payload["quest"], payload["tid"]),
    )


def _task_done(conn, event):
    payload = event["payload"]
    conn.execute(
        "UPDATE quest_tasks SET state = 'done', summary = ?, updated_at = ? WHERE quest = ? AND tid = ?",
        (payload["summary"], event["ts"], payload["quest"], payload["tid"]),
    )


def _task_discarded(conn, event):
    payload = event["payload"]
    conn.execute(
        "UPDATE quest_tasks SET state = 'discarded', discarded_reason = ?, discarded_by = ?, discarded_at = ?,"
        " updated_at = ? WHERE quest = ? AND tid = ?",
        (payload["reason"], payload["author"], event["ts"], event["ts"], payload["quest"], payload["tid"]),
    )


def _task_restored(conn, event):
    payload = event["payload"]
    conn.execute(
        "UPDATE quest_tasks SET state = 'queued', discarded_reason = NULL, discarded_by = NULL, discarded_at = NULL,"
        " updated_at = ? WHERE quest = ? AND tid = ?",
        (event["ts"], payload["quest"], payload["tid"]),
    )


def _task_moved(conn, event):
    payload = event["payload"]
    conn.execute(
        "UPDATE quest_tasks SET quest = ?, updated_at = ? WHERE quest = ? AND tid = ?",
        (payload["to_quest"], event["ts"], payload["from_quest"], payload["tid"]),
    )
    conn.execute(
        "UPDATE quests SET updated_at = ? WHERE slug IN (?, ?)",
        (event["ts"], payload["from_quest"], payload["to_quest"]),
    )
    conn.execute(
        "UPDATE prs SET task_quest = ? WHERE task_quest = ? AND task_tid = ?",
        (payload["to_quest"], payload["from_quest"], payload["tid"]),
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
        " needs_ask_answer, needs_human_pr_review, fixes_main, fixes_flaky, adventurer, tracked_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, NULL, NULL, 0, 0, ?, ?, ?, ?, ?, ?, ?)",
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
            payload.get("adventurer"),
            event["ts"],
        ),
    )


def _pr_set(conn, event):
    payload = event["payload"]
    current = conn.execute(
        "SELECT lifecycle, waits, needs_ask_answer, needs_human_pr_review, last_activity_at,"
        " fixes_main, fixes_flaky, blocked_external, task_quest, task_tid, card FROM prs"
        " WHERE repo = ? AND number = ?",
        (payload["repo"], payload["number"]),
    ).fetchone()
    values = _flags_and_lifecycle(payload, current)
    blocked_external = payload.get("blocked_external", current["blocked_external"])
    links = {field: payload.get(field, current[field]) for field in ("task_quest", "task_tid", "card")}
    changed = (
        any(current[field] != links[field] for field in links)
        or current["waits"] != payload["waits"]
        or current["blocked_external"] != blocked_external
        or any(current[field] != values[field] for field in ("lifecycle",) + _PR_FLAG_FIELDS)
    )
    last_activity_at = event["ts"] if changed else current["last_activity_at"]
    conn.execute(
        "UPDATE prs SET lifecycle = ?, waits = ?, needs_ask_answer = ?, needs_human_pr_review = ?,"
        " fixes_main = ?, fixes_flaky = ?, blocked_external = ?, last_activity_at = ?,"
        " task_quest = ?, task_tid = ?, card = ? WHERE repo = ? AND number = ?",
        (
            values["lifecycle"],
            payload["waits"],
            values["needs_ask_answer"],
            values["needs_human_pr_review"],
            values["fixes_main"],
            values["fixes_flaky"],
            blocked_external,
            last_activity_at,
            links["task_quest"],
            links["task_tid"],
            links["card"],
            payload["repo"],
            payload["number"],
        ),
    )


def _pr_untracked(conn, event):
    payload = event["payload"]
    for table in ("prs", "pr_shared_areas", "pr_files"):
        conn.execute("DELETE FROM {} WHERE repo = ? AND number = ?".format(table), (payload["repo"], payload["number"]))


_PR_SYNCED_CARRY_FORWARD_FIELDS = (
    "mergeable",
    "review_comment_count",
    "checks_pending",
    "review_decision",
    "merge_state",
    "base_branch",
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
    return any(current[field] != _pr_synced_field(current, payload, field) for field in _PR_SYNCED_CARRY_FORWARD_FIELDS)


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
        " head_sha = ?, synced_at = ?, last_activity_at = ?, comments_after_head = ?, ci_label = ?,"
        " checks_billing = ?, trace_valid = ?, trace_reason = ?, other_author_comments = ?"
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
            payload.get("comments_after_head"),
            payload.get("ci_label"),
            payload.get("checks_billing"),
            payload.get("trace_valid"),
            payload.get("trace_reason"),
            payload.get("other_author_comments"),
            payload["repo"],
            payload["number"],
        ),
    )
    if "change_set" in payload:
        _store_change_set(conn, payload["repo"], payload["number"], payload["change_set"])


def _store_change_set(conn, repo, number, change_set):
    conn.execute(
        "UPDATE prs SET additions = ?, deletions = ?, created_at = ? WHERE repo = ? AND number = ?",
        (change_set["additions"], change_set["deletions"], change_set["created_at"], repo, number),
    )
    conn.execute("DELETE FROM pr_shared_areas WHERE repo = ? AND number = ?", (repo, number))
    for glob in change_set["globs"]:
        conn.execute("INSERT INTO pr_shared_areas (repo, number, glob) VALUES (?, ?, ?)", (repo, number, glob))
    if "paths" not in change_set:
        return
    conn.execute("DELETE FROM pr_files WHERE repo = ? AND number = ?", (repo, number))
    for path in change_set["paths"]:
        conn.execute("INSERT INTO pr_files (repo, number, path) VALUES (?, ?, ?)", (repo, number, path))


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
        " snapshot, recommend) VALUES (?, ?, ?, ?, ?, ?, 'open', NULL, ?, ?, ?)",
        (
            payload["id"],
            payload["party"],
            payload["question"],
            payload["context"],
            _dump(payload["refs"]),
            _dump(payload["options"]),
            event["ts"],
            _snapshot_json(payload.get("snapshot")),
            payload.get("recommend"),
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


_IDEA_COLUMNS = ("title", "description", "requester", "deadline", "project")


def _idea_created(conn, event):
    payload = event["payload"]
    conn.execute(
        "INSERT INTO ideas (id, title, description, requester, deadline, project, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            payload["id"],
            payload["title"],
            payload["description"],
            payload["requester"],
            payload["deadline"],
            payload["project"],
            event["ts"],
            event["ts"],
        ),
    )


def _idea_edited(conn, event):
    payload = event["payload"]
    columns = [column for column in _IDEA_COLUMNS if column in payload["fields"]]
    assignments = ", ".join("{} = ?".format(column) for column in columns)
    values = [payload["fields"][column] for column in columns]
    conn.execute(
        "UPDATE ideas SET {}, updated_at = ? WHERE id = ?".format(assignments),
        values + [event["ts"], payload["id"]],
    )


def _idea_deleted(conn, event):
    conn.execute("DELETE FROM ideas WHERE id = ?", (event["payload"]["id"],))
    conn.execute("DELETE FROM idea_links WHERE idea_id = ?", (event["payload"]["id"],))
    conn.execute("DELETE FROM idea_adventurer_links WHERE idea_id = ?", (event["payload"]["id"],))


def _idea_linked(conn, event):
    payload = event["payload"]
    conn.execute(
        "INSERT OR IGNORE INTO idea_links (idea_id, party, linked_at) VALUES (?, ?, ?)",
        (payload["id"], payload["party"], event["ts"]),
    )


def _idea_unlinked(conn, event):
    payload = event["payload"]
    conn.execute("DELETE FROM idea_links WHERE idea_id = ? AND party = ?", (payload["id"], payload["party"]))


def _idea_adventurer_linked(conn, event):
    payload = event["payload"]
    conn.execute(
        "INSERT OR IGNORE INTO idea_adventurer_links (idea_id, adventurer, linked_at) VALUES (?, ?, ?)",
        (payload["id"], payload["adventurer"], event["ts"]),
    )


def _idea_adventurer_unlinked(conn, event):
    payload = event["payload"]
    conn.execute(
        "DELETE FROM idea_adventurer_links WHERE idea_id = ? AND adventurer = ?", (payload["id"], payload["adventurer"])
    )


def _claim_created(conn, event):
    payload = event["payload"]
    conn.execute(
        "INSERT INTO claims (project, area, party, expires_at, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)"
        " ON CONFLICT(project, area) DO UPDATE SET"
        " created_at = CASE WHEN claims.party = excluded.party THEN claims.created_at ELSE excluded.created_at END,"
        " party = excluded.party, expires_at = excluded.expires_at, updated_at = excluded.updated_at",
        (payload["project"], payload["area"], payload["party"], payload["expires_at"], event["ts"], event["ts"]),
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
        "INSERT INTO raid_members (raid, party, expires_at) VALUES (?, ?, ?)"
        " ON CONFLICT(raid, party) DO UPDATE SET expires_at = excluded.expires_at",
        (payload["raid"], payload["party"], payload["expires_at"]),
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


def _base_paused(conn, event):
    conn.execute(
        "INSERT OR REPLACE INTO base_pauses (repo, paused_at) VALUES (?, ?)",
        (event["payload"]["repo"], event["ts"]),
    )


def _base_resumed(conn, event):
    conn.execute("DELETE FROM base_pauses WHERE repo = ?", (event["payload"]["repo"],))


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


def _dependabot_synced(conn, event):
    payload = event["payload"]
    conn.execute(
        "INSERT OR REPLACE INTO dependabot_status (repo, unmergeable, run_failed, updated_at) VALUES (?, ?, ?, ?)",
        (payload["repo"], payload["unmergeable"], 1 if payload["run_failed"] else 0, event["ts"]),
    )
    conn.execute("DELETE FROM dependabot_ready WHERE repo = ?", (payload["repo"],))
    conn.executemany(
        "INSERT INTO dependabot_ready (repo, number, title) VALUES (?, ?, ?)",
        [(payload["repo"], entry["number"], entry["title"]) for entry in payload.get("ready", [])],
    )


def _dependabot_announced(conn, event):
    payload = event["payload"]
    conn.execute(
        "INSERT OR IGNORE INTO dependabot_announced (repo, number) VALUES (?, ?)", (payload["repo"], payload["number"])
    )


def _solo_launched(conn, event):
    payload = event["payload"]
    conn.execute(
        "INSERT OR REPLACE INTO solo_launches (health_job, launched_at, trigger) VALUES (?, ?, ?)",
        (solo_players.health_job_name(payload["repo"], payload["job"]), event["ts"], payload.get("trigger")),
    )


def _solo_paused(conn, event):
    payload = event["payload"]
    conn.execute(
        "INSERT OR REPLACE INTO solo_pauses (health_job, paused_at) VALUES (?, ?)",
        (solo_players.health_job_name(payload["repo"], payload["job"]), event["ts"]),
    )


def _solo_resumed(conn, event):
    payload = event["payload"]
    conn.execute(
        "DELETE FROM solo_pauses WHERE health_job = ?", (solo_players.health_job_name(payload["repo"], payload["job"]),)
    )


def _solo_message(conn, event):
    payload = event["payload"]
    conn.execute(
        "INSERT INTO solo_messages (health_job, ts, text) VALUES (?, ?, ?)",
        (solo_players.health_job_name(payload["repo"], payload["job"]), event["ts"], payload["text"]),
    )


def _main_marked(conn, event):
    _record_main_status(conn, event, "manual")


_WAIT_STATUS = {
    "permission": "waiting-permission",
    "elicitation": "waiting-permission",
    "idle": "waiting-input",
}


def _adventurer_started(conn, event):
    payload = event["payload"]
    conn.execute(
        "INSERT INTO adventurers (id, session_id, project, job, task, health_job, state, pending, started_at, done_at, reason)"
        " VALUES (?, ?, ?, ?, ?, ?, 'active', NULL, ?, NULL, ?)",
        (
            payload["id"],
            event["session_id"],
            event["project"],
            payload["job"],
            payload["task"],
            payload.get("health_job"),
            event["ts"],
            payload.get("reason"),
        ),
    )


def _adventurer_promoted(conn, event):
    payload = event["payload"]
    conn.execute(
        "UPDATE adventurers SET state = 'promoted', pending = ?, done_at = ? WHERE id = ?",
        ("promoted to party {}".format(payload["party"]), event["ts"], payload["id"]),
    )
    conn.execute(
        "UPDATE prs SET party = ? WHERE adventurer = ? AND party = ''",
        (payload["party"], payload["id"]),
    )
    conn.execute(
        "INSERT OR IGNORE INTO idea_links (idea_id, party, linked_at)"
        " SELECT idea_id, ?, linked_at FROM idea_adventurer_links WHERE adventurer = ?",
        (payload["party"], payload["id"]),
    )
    conn.execute("DELETE FROM idea_adventurer_links WHERE adventurer = ?", (payload["id"],))


def _close_open_quest_task(conn, event, task):
    if task is None or "/" not in task:
        return
    quest, tid = task.split("/", 1)
    row = conn.execute("SELECT 1 FROM quests WHERE slug = ? AND epic IS NULL AND party IS NULL", (quest,)).fetchone()
    if row is None:
        return
    conn.execute(
        "UPDATE quest_tasks SET state = 'done', updated_at = ? WHERE quest = ? AND tid = ?", (event["ts"], quest, tid)
    )
    unfinished = conn.execute(
        "SELECT 1 FROM quest_tasks WHERE quest = ? AND state != 'done' LIMIT 1", (quest,)
    ).fetchone()
    if unfinished is None:
        conn.execute("UPDATE quests SET state = 'done', updated_at = ? WHERE slug = ?", (event["ts"], quest))


def _adventurer_done(conn, event):
    payload = event["payload"]
    conn.execute(
        "UPDATE adventurers SET state = 'done', pending = ?, done_at = ? WHERE id = ?",
        (payload["pending"], event["ts"], payload["id"]),
    )
    adventurer = conn.execute("SELECT task FROM adventurers WHERE id = ?", (payload["id"],)).fetchone()
    _close_open_quest_task(conn, event, adventurer["task"])


def _adventurer_dismissed(conn, event):
    conn.execute("UPDATE adventurers SET state = 'dismissed' WHERE id = ?", (event["payload"]["id"],))


def _set_session_status(conn, event, status, detail):
    conn.execute(
        "INSERT OR REPLACE INTO session_status (session_id, party, status, detail, since) VALUES (?, ?, ?, ?, ?)",
        (event["session_id"], event["party"] or "", status, detail, event["ts"]),
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


def _db_compacted(conn, event):
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
        " load1, load5, load15, cpu_count, guild_db_bytes, docker_images, docker_images_reclaimable,"
        " docker_containers, docker_volumes, docker_build_cache)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            event["ts"],
            machine["disk_total"],
            machine["disk_used"],
            machine["mem_total"],
            machine["mem_available"],
            machine.get("load1"),
            machine.get("load5"),
            machine.get("load15"),
            machine.get("cpu_count"),
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
        "INSERT OR IGNORE INTO findings (project, class, repo, number, party, recorded_at) VALUES (?, ?, ?, ?, ?, ?)",
        (payload["project"], payload["class"], payload["repo"], payload["number"], payload["party"], event["ts"]),
    )


_REDUCERS = {
    "party.started": _party_started,
    "party.resumed": _party_resumed,
    "party.closed": _party_closed,
    "party.handed_off": _party_handed_off,
    "party.parked": _party_parked,
    "party.unparked": _party_unparked,
    "handoff.pruned": _handoff_pruned,
    "leader.located": _leader_located,
    "leader.window_launched": _leader_window_launched,
    "leader.window_recorded": _leader_window_launched,
    "health_window.launched": _health_window_launched,
    "quest.added": _quest_added,
    "quest.done": _quest_done,
    "quest.taken": _quest_taken,
    "quest.released": _quest_released,
    "quest.marked_incomplete": _quest_marked_incomplete,
    "task.added": _task_added,
    "task.started": _task_started,
    "task.blocked": _task_blocked,
    "task.done": _task_done,
    "task.discarded": _task_discarded,
    "task.restored": _task_restored,
    "task.moved": _task_moved,
    "epic.synced": _epic_synced,
    "tracker.synced": _tracker_synced,
    "finding.recorded": _finding_recorded,
    "pr.tracked": _pr_tracked,
    "pr.set": _pr_set,
    "pr.untracked": _pr_untracked,
    "pr.synced": _pr_synced,
    "pr.comments_acknowledged": _pr_comments_acknowledged,
    "ask.created": _ask_created,
    "ask.answered": _ask_answered,
    "ask.dismissed": _ask_dismissed,
    "notice.created": _notice_created,
    "notice.closed": _notice_closed,
    "notice.seen": _notice_seen,
    "notice.unseen": _notice_unseen,
    "idea.created": _idea_created,
    "idea.edited": _idea_edited,
    "idea.deleted": _idea_deleted,
    "idea.linked": _idea_linked,
    "idea.unlinked": _idea_unlinked,
    "idea.adventurer_linked": _idea_adventurer_linked,
    "idea.adventurer_unlinked": _idea_adventurer_unlinked,
    "adventurer.started": _adventurer_started,
    "adventurer.done": _adventurer_done,
    "adventurer.promoted": _adventurer_promoted,
    "adventurer.dismissed": _adventurer_dismissed,
    "claim.created": _claim_created,
    "claim.released": _claim_released,
    "raid.joined": _raid_joined,
    "raid.left": _raid_left,
    "raid.paused": _raid_paused,
    "base.paused": _base_paused,
    "base.resumed": _base_resumed,
    "raid.resumed": _raid_resumed,
    "merge_queue.pinned": _merge_queue_pinned,
    "merge_queue.unpinned": _merge_queue_unpinned,
    "main.status_synced": _main_status_synced,
    "dependabot.synced": _dependabot_synced,
    "dependabot.announced": _dependabot_announced,
    "solo.launched": _solo_launched,
    "solo.message": _solo_message,
    "solo.paused": _solo_paused,
    "solo.resumed": _solo_resumed,
    "main.marked": _main_marked,
    "session.waiting": _session_waiting,
    "session.stopped": _session_stopped,
    "session.working": _session_working,
    "cost.sampled": _cost_sampled,
    "lifecycle.ran": _lifecycle_ran,
    "resources.sampled": _resources_sampled,
    "db.compacted": _db_compacted,
}


def _retired(conn, event):
    return None


_REDUCERS.update(
    {
        kind: _retired
        for kind in (
            "dispatch.paused",
            "dispatch.resumed",
            "dispatch.decided",
            "dispatch.launched",
            "dispatch.launch_failed",
            "dispatch.bound",
            "pr.fix_requested",
        )
    }
)


_REQUIRED_KEYS = {
    "party.started": ("party", "session_name"),
    "party.resumed": ("party", "generation", "session_name"),
    "party.closed": ("party", "generation"),
    "party.handed_off": ("party", "handoff_path", "generation"),
    "party.parked": ("party", "reason"),
    "party.unparked": ("party",),
    "handoff.pruned": ("party", "generation"),
    "leader.located": ("cwd", "permission_mode", "party", "generation"),
    "leader.window_launched": ("party", "generation", "window_id"),
    "leader.window_recorded": ("party", "generation", "window_id"),
    "health_window.launched": ("window_id",),
    "quest.added": ("slug", "project", "party", "epic", "title", "tasks"),
    "quest.done": ("slug",),
    "quest.taken": ("party", "slug"),
    "quest.released": ("slug", "party"),
    "quest.marked_incomplete": (),
    "task.added": ("quest", "tid", "title"),
    "task.started": ("summary", "quest", "tid"),
    "task.blocked": ("reason", "quest", "tid"),
    "task.done": ("summary", "quest", "tid"),
    "task.discarded": ("quest", "tid", "reason", "author"),
    "task.restored": ("quest", "tid"),
    "task.moved": ("to_quest", "from_quest", "tid"),
    "epic.synced": ("project", "epic", "sdd_path", "tasks"),
    "tracker.synced": ("project", "cards"),
    "finding.recorded": ("project", "class", "repo", "number", "party"),
    "pr.tracked": (
        "lifecycle",
        "repo",
        "number",
        "party",
        "task_quest",
        "task_tid",
        "what",
        "waits",
        "branch",
        "title",
        "gh_state",
        "gh_draft",
        "seeded",
    ),
    "pr.set": ("lifecycle", "repo", "number", "waits"),
    "pr.untracked": ("repo", "number"),
    "pr.synced": (
        "lifecycle",
        "gh_state",
        "gh_draft",
        "branch",
        "title",
        "checks_failing",
        "checks_passing",
        "synced_at",
        "repo",
        "number",
    ),
    "pr.comments_acknowledged": ("repo", "number"),
    "ask.created": ("id", "party", "question", "context", "refs", "options"),
    "ask.answered": ("answer", "id"),
    "ask.dismissed": ("id",),
    "notice.created": ("id", "party", "scope", "text", "until_condition", "expires_at"),
    "notice.closed": ("id",),
    "notice.seen": ("id",),
    "notice.unseen": ("id",),
    "idea.created": ("id", "title", "description", "requester", "deadline", "project"),
    "idea.edited": ("fields", "id"),
    "idea.deleted": ("id",),
    "idea.linked": ("id", "party"),
    "idea.unlinked": ("id", "party"),
    "idea.adventurer_linked": ("adventurer", "id"),
    "idea.adventurer_unlinked": ("adventurer", "id"),
    "adventurer.started": ("id", "job", "task"),
    "adventurer.done": ("pending", "id"),
    "adventurer.promoted": ("party", "id"),
    "adventurer.dismissed": ("id",),
    "claim.created": ("project", "area", "party", "expires_at"),
    "claim.released": ("project", "area"),
    "raid.joined": ("raid", "party", "expires_at"),
    "raid.left": ("raid", "party"),
    "raid.paused": ("raid", "party"),
    "base.paused": ("repo",),
    "base.resumed": ("repo",),
    "raid.resumed": ("raid",),
    "merge_queue.pinned": ("first_repo", "first_number", "second_repo", "second_number", "author"),
    "merge_queue.unpinned": ("first_repo", "first_number", "second_repo", "second_number"),
    "main.status_synced": ("repo", "red", "reason"),
    "dependabot.synced": ("repo", "unmergeable", "run_failed"),
    "dependabot.announced": ("repo", "number"),
    "solo.launched": ("repo", "job"),
    "solo.message": ("repo", "job", "text"),
    "solo.paused": ("repo", "job"),
    "solo.resumed": ("repo", "job"),
    "main.marked": ("repo", "red", "reason"),
    "session.waiting": ("wait", "message"),
    "session.stopped": (),
    "session.working": (),
    "cost.sampled": (
        "day",
        "model",
        "quest",
        "tid",
        "input_tokens",
        "cache_creation_tokens",
        "cache_read_tokens",
        "output_tokens",
    ),
    "lifecycle.ran": (),
    "resources.sampled": ("items", "machine"),
    "db.compacted": (),
}

_REQUIRED_KEYS.update(
    {
        kind: ()
        for kind in (
            "dispatch.paused",
            "dispatch.resumed",
            "dispatch.decided",
            "dispatch.launched",
            "dispatch.launch_failed",
            "dispatch.bound",
            "pr.fix_requested",
        )
    }
)


def required_keys(kind):
    if kind not in _REQUIRED_KEYS:
        raise GuildError("unknown event kind: {}".format(kind), 1)
    return _REQUIRED_KEYS[kind]


def apply(conn, event):
    _REDUCERS[event["kind"]](conn, event)
