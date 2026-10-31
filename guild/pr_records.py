import json

from guild import (
    main_status,
    merge_queue,
    pr_asks,
    resolve,
    sanitize,
)


def ref_text(repo, number):
    return "{}#{}".format(repo, number)


def _task_context(conn, row):
    if row["task_quest"] is None:
        return None
    quest = conn.execute("SELECT project, epic FROM quests WHERE slug = ?", (row["task_quest"],)).fetchone()
    if quest is None or quest["epic"] is None:
        return None
    return quest["project"], quest["epic"]


def _task_deps(conn, project, epic, tid):
    task = conn.execute(
        "SELECT deps FROM tasks WHERE project = ? AND epic = ? AND tid = ?", (project, epic, tid)
    ).fetchone()
    if task is None:
        return []
    return json.loads(task["deps"])


def _unmet_deps(conn, project, epic, deps):
    return [dep for dep in deps if not resolve.resolve_task_done(conn, project, epic, dep)[0]]


def _globs(conn, row):
    rows = conn.execute(
        "SELECT glob FROM pr_shared_areas WHERE repo = ? AND number = ? ORDER BY glob",
        (row["repo"], row["number"]),
    ).fetchall()
    return [glob_row["glob"] for glob_row in rows]


def _optional_branch(branch):
    if not branch:
        return None
    return sanitize.strip_control_sequences(branch)


def _pr_record(conn, row):
    context = _task_context(conn, row)
    task_key = None
    dep_keys = []
    unmet = []
    if context is not None:
        project, epic = context
        deps = _task_deps(conn, project, epic, row["task_tid"])
        task_key = (project, epic, row["task_tid"])
        dep_keys = [(project, epic, dep) for dep in deps]
        unmet = _unmet_deps(conn, project, epic, deps)
    return {
        "ref": ref_text(row["repo"], row["number"]),
        "repo": row["repo"],
        "number": row["number"],
        "party": row["party"],
        "quest": row["task_quest"],
        "tid": row["task_tid"],
        "card": row["card"],
        "lifecycle": row["lifecycle"],
        "checks_failing": row["checks_failing"] or 0,
        "checks_billing": row["checks_billing"],
        "checks_passing": row["checks_passing"] or 0,
        "checks_pending": row["checks_pending"] or 0,
        "needs_ask_answer": pr_asks.needs_answer(row),
        "ask_id": row["open_ask_id"],
        "needs_human_pr_review": bool(row["needs_human_pr_review"]),
        "branch": _optional_branch(row["branch"]),
        "base_branch": _optional_branch(row["base_branch"]),
        "fixes_main": bool(row["fixes_main"]),
        "fixes_flaky": bool(row["fixes_flaky"]),
        "blocked_external": row["blocked_external"],
        "mergeable": row["mergeable"],
        "review_decision": row["review_decision"],
        "unresolved_threads": row["unresolved_threads"],
        "comments_after_head": row["comments_after_head"],
        "unseen_comments": max(0, (row["review_comment_count"] or 0) - (row["last_notified_comment_count"] or 0)),
        "ci_label": row["ci_label"],
        "trace_valid": row["trace_valid"],
        "trace_reason": row["trace_reason"],
        "merge_state": row["merge_state"],
        "additions": row["additions"] or 0,
        "deletions": row["deletions"] or 0,
        "created_at": row["created_at"],
        "globs": _globs(conn, row),
        "task_key": task_key,
        "dep_keys": dep_keys,
        "unmet_deps": unmet,
        "synced_at": row["synced_at"],
    }


def open_pr_records(conn):
    rows = conn.execute(
        pr_asks.PRS_WITH_ASK_SQL + " WHERE lifecycle NOT IN ('merged', 'closed') ORDER BY repo ASC, number ASC"
    ).fetchall()
    return [_pr_record(conn, row) for row in rows]


def load_pins(conn):
    rows = conn.execute(
        "SELECT * FROM merge_queue_pins ORDER BY first_repo, first_number, second_repo, second_number"
    ).fetchall()
    return [
        {
            "first": ref_text(row["first_repo"], row["first_number"]),
            "second": ref_text(row["second_repo"], row["second_number"]),
            "author": row["party"],
        }
        for row in rows
    ]


def load_scoped_queue(conn, party_names):
    return merge_queue.scoped_queue(open_pr_records(conn), load_pins(conn), main_status.red_rows(conn), party_names)


def external_blocked_refs(conn):
    queue = merge_queue.compute(open_pr_records(conn), load_pins(conn), [])["queue"]
    return {entry["ref"] for entry in queue if entry["external"] is not None}
