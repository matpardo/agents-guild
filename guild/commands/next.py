import json
from datetime import timedelta

from guild import config, events, resolve, timeutil
from guild.commands import pr as pr_commands


def _own_open_prs(conn, party):
    return conn.execute(
        "SELECT * FROM prs WHERE party = ? AND lifecycle NOT IN ('merged', 'closed')"
        " ORDER BY repo ASC, number ASC",
        (party,),
    ).fetchall()


def _last_pr_set_ts(conn, repo, number):
    last = None
    for event in events.all_events(conn):
        if event["kind"] != "pr.set":
            continue
        payload = event["payload"]
        if payload["repo"] == repo and payload["number"] == number:
            last = event["ts"]
    return last


def _ask_answered_ts(conn, ask_id):
    last = None
    for event in events.all_events(conn):
        if event["kind"] != "ask.answered" or event["payload"]["id"] != ask_id:
            continue
        last = event["ts"]
    return last


def _latest_answered_ask_for_ref(conn, ref):
    rows = conn.execute("SELECT * FROM asks WHERE state = 'answered' ORDER BY id ASC").fetchall()
    best = None
    for row in rows:
        if ref not in json.loads(row["refs"]):
            continue
        answered_at = _ask_answered_ts(conn, row["id"])
        if answered_at is None:
            continue
        if best is None or answered_at > best["answered_at"]:
            best = {"id": row["id"], "answer": row["answer"], "answered_at": answered_at}
    return best


def _open_ask_id_for_ref(conn, ref):
    rows = conn.execute("SELECT id, refs FROM asks WHERE state = 'open' ORDER BY id ASC").fetchall()
    for row in rows:
        if ref in json.loads(row["refs"]):
            return row["id"]
    return None


def _tier1_candidates(conn, party):
    results = []
    for row in _own_open_prs(conn, party):
        if (row["checks_failing"] or 0) > 0:
            results.append((row, "failing checks ({} failing)".format(row["checks_failing"]), False))
            continue
        if row["mergeable"] == "CONFLICTING":
            results.append((row, "merge conflict", False))
            continue
        unseen = (row["review_comment_count"] or 0) - (row["last_notified_comment_count"] or 0)
        if unseen > 0:
            results.append((row, "new review comments ({} unseen)".format(unseen), True))
    return results


def _tier2_candidates(conn, party):
    results = []
    for row in _own_open_prs(conn, party):
        if row["lifecycle"] != "needs-human":
            continue
        ref = "pr:{}#{}".format(row["repo"], row["number"])
        answered = _latest_answered_ask_for_ref(conn, ref)
        if answered is None:
            continue
        last_set_ts = _last_pr_set_ts(conn, row["repo"], row["number"])
        if last_set_ts is not None and answered["answered_at"] <= last_set_ts:
            continue
        reason = "ask #{} answered: {}".format(answered["id"], answered["answer"])
        results.append((row, reason, False))
    return results


def _tier3_candidates(conn, now, party, stale_hours):
    if stale_hours is None:
        return []
    threshold = timedelta(hours=stale_hours)
    results = []
    for row in _own_open_prs(conn, party):
        if row["lifecycle"] != "converging" or not row["last_activity_at"]:
            continue
        idle = now - timeutil.from_iso(row["last_activity_at"])
        if idle <= threshold:
            continue
        hours = int(idle.total_seconds() // 3600)
        reason = "converging with no activity for {}h (> {}h)".format(hours, stale_hours)
        results.append((row, reason, False))
    return results


def _stale_hours(projects_dir, project):
    if project is None:
        return None
    project_data = config.load_project(projects_dir, project)
    next_config = project_data.get("next")
    if next_config is None:
        return None
    return next_config.get("stale_hours")


def _claim_area(item):
    if item["epic"] is not None:
        return "task:{}/{}".format(item["epic"], item["tid"])
    return "task:{}/{}".format(item["quest"], item["tid"])


def _claim_holder(conn, now, project, area, party):
    row = conn.execute(
        "SELECT party, expires_at FROM claims WHERE project = ? AND area = ?", (project, area)
    ).fetchone()
    if row is None or timeutil.is_expired(now, row["expires_at"]) or row["party"] == party:
        return None
    return row["party"]


def _queued_tasks(conn, project, party):
    quest_rows = conn.execute(
        "SELECT slug, epic FROM quests WHERE party = ? AND state = 'active' ORDER BY slug ASC", (party,)
    ).fetchall()
    items = []
    for quest_row in quest_rows:
        task_rows = conn.execute(
            "SELECT tid, title FROM quest_tasks WHERE quest = ? AND state = 'queued' ORDER BY tid ASC",
            (quest_row["slug"],),
        ).fetchall()
        for task_row in task_rows:
            order_idx, deps = None, []
            if quest_row["epic"] is not None:
                observed = conn.execute(
                    "SELECT order_idx, deps FROM tasks WHERE project = ? AND epic = ? AND tid = ?",
                    (project, quest_row["epic"], task_row["tid"]),
                ).fetchone()
                if observed is not None:
                    order_idx, deps = observed["order_idx"], json.loads(observed["deps"])
            items.append(
                {
                    "quest": quest_row["slug"],
                    "epic": quest_row["epic"],
                    "tid": task_row["tid"],
                    "title": task_row["title"],
                    "order_idx": order_idx,
                    "deps": deps,
                }
            )
    items.sort(key=lambda item: (item["order_idx"] is None, item["order_idx"] or 0, item["tid"]))
    return items


def _disagreement_line(epic, tid, disagreements):
    parts = ", ".join("{}={}".format(source, "done" if opinion else "pending") for source, opinion in disagreements)
    return "{}/{}: {}".format(epic, tid, parts)


def _evaluate_next_task(conn, now, project, party):
    disagreements = []
    blocked = []
    for item in _queued_tasks(conn, project, party):
        if item["epic"] is not None and item["deps"]:
            pending = []
            for dep_tid in item["deps"]:
                is_done, source, dep_disagreements = resolve.resolve_task_done(
                    conn, project, item["epic"], dep_tid
                )
                if dep_disagreements:
                    disagreements.append(_disagreement_line(item["epic"], dep_tid, dep_disagreements))
                if not is_done:
                    pending.append("{} (per {})".format(dep_tid, source or "no source"))
            if pending:
                blocked.append(
                    "{}/{}: waiting on {}".format(item["quest"], item["tid"], ", ".join(pending))
                )
                continue
        ref = "task:{}/{}".format(item["quest"], item["tid"])
        ask_id = _open_ask_id_for_ref(conn, ref)
        if ask_id is not None:
            blocked.append("{}/{}: open ask #{}".format(item["quest"], item["tid"], ask_id))
            continue
        holder = _claim_holder(conn, now, project, _claim_area(item), party)
        if holder is not None:
            blocked.append("{}/{}: claimed by {}".format(item["quest"], item["tid"], holder))
            continue
        return item, disagreements, blocked
    return None, disagreements, blocked


def _pr_label(row):
    return "{}#{}".format(row["repo"], row["number"])


def _task_title_display(next_task):
    if next_task["epic"] is not None:
        return '"{}"'.format(next_task["title"])
    return next_task["title"]


def _render_all(tier1, tier2, tier3, next_task, disagreements):
    lines = []
    for row, reason, _ in tier1 + tier2 + tier3:
        lines.append("PR {}: {}".format(_pr_label(row), reason))
    if next_task is not None:
        lines.append(
            "task {}/{}: {} — ready".format(
                next_task["quest"], next_task["tid"], _task_title_display(next_task)
            )
        )
    for line in disagreements:
        lines.append("disagreement: {}".format(line))
    if not lines:
        lines.append("nothing actionable")
    return lines


def _render_single(ctx, tier1, tier2, tier3, next_task, disagreements, blocked, acknowledge):
    for candidates in (tier1, tier2, tier3):
        if not candidates:
            continue
        row, reason, should_ack = candidates[0]
        if should_ack and acknowledge:
            pr_commands.acknowledge_comments(ctx, row["repo"], row["number"])
        lines = ["PR {}: {}".format(_pr_label(row), reason)]
        for line in disagreements:
            lines.append("disagreement: {}".format(line))
        return lines
    if next_task is not None:
        lines = [
            "task {}/{}: {} — ready".format(
                next_task["quest"], next_task["tid"], _task_title_display(next_task)
            )
        ]
        for line in disagreements:
            lines.append("disagreement: {}".format(line))
        return lines
    lines = ["nothing actionable"]
    lines.extend(blocked)
    for line in disagreements:
        lines.append("disagreement: {}".format(line))
    return lines


def run(ctx, binding, show_all, acknowledge):
    party, project = binding["party"], binding["project"]
    stale_hours = _stale_hours(ctx.projects_dir, project)

    tier1 = _tier1_candidates(ctx.conn, party)
    tier2 = _tier2_candidates(ctx.conn, party)
    tier3 = _tier3_candidates(ctx.conn, ctx.now, party, stale_hours)
    if project is None:
        next_task, disagreements, blocked = None, [], []
    else:
        next_task, disagreements, blocked = _evaluate_next_task(ctx.conn, ctx.now, project, party)

    if show_all:
        return _render_all(tier1, tier2, tier3, next_task, disagreements)
    return _render_single(ctx, tier1, tier2, tier3, next_task, disagreements, blocked, acknowledge)
