import json
from datetime import timedelta

from guild import config, merge_queue, pr_asks, resolve, sanitize, timeutil
from guild.commands import drift as drift_commands
from guild.commands import merge_queue as merge_queue_commands
from guild.commands import pr as pr_commands
from guild.commands import quest as quest_commands
from guild.commands import raid as raid_commands


def _without_external(conn, rows):
    external = merge_queue_commands.external_blocked_refs(conn)
    return [row for row in rows if "{}#{}".format(row["repo"], row["number"]) not in external]


def _own_open_prs(conn, party):
    rows = conn.execute(
        pr_asks.PRS_WITH_ASK_SQL + " WHERE party = ? AND lifecycle NOT IN ('merged', 'closed')"
        " ORDER BY repo ASC, number ASC",
        (party,),
    ).fetchall()
    return _without_external(conn, rows)


def _last_pr_set_ts(conn, repo, number):
    row = conn.execute(
        "SELECT MAX(ts) AS ts FROM events WHERE kind = 'pr.set'"
        " AND json_extract(payload, '$.repo') = ? AND json_extract(payload, '$.number') = ?",
        (repo, number),
    ).fetchone()
    return row["ts"]


def _ask_answered_ts(conn, ask_id):
    row = conn.execute(
        "SELECT MAX(ts) AS ts FROM events WHERE kind = 'ask.answered' AND json_extract(payload, '$.id') = ?",
        (ask_id,),
    ).fetchone()
    return row["ts"]


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


def _tier0_candidates(conn, party):
    results = []
    for row in _own_open_prs(conn, party):
        if not merge_queue.unblocks_everyone(row):
            continue
        results.append((row, "{} — land it first".format(merge_queue.urgency_clause(row)), False))
    return results


def _tier1_candidates(conn, party):
    results = []
    for row in _own_open_prs(conn, party):
        if (row["checks_failing"] or 0) > 0 and not row["checks_billing"]:
            results.append((row, "failing checks ({} failing)".format(row["checks_failing"]), False))
            continue
        reasons = merge_queue.review_reasons(
            row["mergeable"], row["review_decision"], row["unresolved_threads"], row["merge_state"]
        )
        if reasons:
            results.append((row, "; ".join(reasons), False))
            continue
        unseen = (row["review_comment_count"] or 0) - (row["last_notified_comment_count"] or 0)
        if unseen > 0:
            results.append((row, "new review comments ({} unseen)".format(unseen), True))
    return results


def _tier2_candidates(conn, party):
    results = []
    for row in _own_open_prs(conn, party):
        if not row["needs_ask_answer"]:
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


def _cap(projects_dir, project, key):
    return config.load_project(projects_dir, project).get(key)


def _project_parties(conn, project):
    rows = conn.execute("SELECT name FROM parties WHERE project = ?", (project,)).fetchall()
    return {row["name"] for row in rows}


def _scope_open_prs(conn, parties):
    marks = ",".join("?" * len(parties))
    rows = conn.execute(
        "SELECT * FROM prs WHERE party IN ({}) AND lifecycle NOT IN ('merged', 'closed')"
        " ORDER BY repo ASC, number ASC".format(marks),
        sorted(parties),
    ).fetchall()
    return _without_external(conn, rows)


def _wait_line(conn, parties, scope_label, open_prs):
    queue = merge_queue_commands.load_scoped_queue(conn, parties)["queue"]
    first = next((entry["ref"] for entry in queue if entry["external"] is None), _pr_label(open_prs[0]))
    return "wait: {} open PRs{}, merge {} first".format(len(open_prs), scope_label, first)


def cap_status(conn, projects_dir, party, project):
    party_cap = _cap(projects_dir, project, "max_open_prs_per_party")
    project_cap = _cap(projects_dir, project, "max_open_prs")
    own_open = _own_open_prs(conn, party)
    parties = _project_parties(conn, project)
    project_open = _scope_open_prs(conn, parties)
    party_wait = None
    if party_cap is not None and len(own_open) >= party_cap:
        party_wait = _wait_line(conn, {party}, "", own_open)
    project_wait = None
    if project_cap is not None and len(project_open) >= project_cap:
        project_wait = _wait_line(conn, parties, " in project", project_open)
    return {
        "party_open": len(own_open),
        "party_cap": party_cap,
        "party_wait": party_wait,
        "project_open": len(project_open),
        "project_cap": project_cap,
        "project_wait": project_wait,
    }


def _cap_wait_line(ctx, party, project):
    status = cap_status(ctx.conn, ctx.projects_dir, party, project)
    return status["party_wait"] or status["project_wait"]


def _unfixable_no_checks(entry):
    return (
        entry["ci_label"] is None
        and entry["human_missing"] == [merge_queue.NO_CHECKS_MISSING]
        and not entry["blockers"]
        and not entry["waits"]
    )


def _wip_line(ctx, party):
    if not any(row["lifecycle"] == "ready" for row in _own_open_prs(ctx.conn, party)):
        return None
    queue = merge_queue_commands.load_scoped_queue(ctx.conn, {party})["queue"]
    for entry in queue:
        if entry["external"] is not None or entry["lifecycle"] != "ready":
            continue
        if entry["human_state"] in merge_queue.HUMAN_READY_STATES or _unfixable_no_checks(entry):
            continue
        missing = sanitize.strip_control_sequences("; ".join(entry["human_missing"] or entry["reasons"]))
        return "wait: {} is not human-ready ({}), resolve it first".format(entry["ref"], missing)
    return None


def claim_area(item):
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
        "SELECT slug, project, epic FROM quests WHERE party = ? AND state = 'active' ORDER BY slug ASC", (party,)
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
                    "quest_row": quest_row,
                    "epic": quest_row["epic"],
                    "tid": task_row["tid"],
                    "title": task_row["title"],
                    "order_idx": order_idx,
                    "deps": deps,
                }
            )
    items.sort(key=lambda item: (item["order_idx"] is None, item["order_idx"] or 0, item["tid"]))
    return items


def _open_quest_offer(conn, project, party):
    if project is None or _queued_tasks(conn, project, party):
        return None
    row = conn.execute(
        "SELECT slug FROM quests WHERE project = ? AND party IS NULL AND state = 'active' ORDER BY rowid ASC",
        (project,),
    ).fetchone()
    if row is None:
        return None
    return "take open quest {}".format(row["slug"])


def _disagreement_line(epic, tid, disagreements):
    parts = ", ".join("{}={}".format(source, "done" if opinion else "pending") for source, opinion in disagreements)
    return "{}/{}: {}".format(epic, tid, parts)


def _evaluate_next_task(conn, now, project, party):
    disagreements = []
    blocked = []
    for item in _queued_tasks(conn, project, party):
        if quest_commands.task_adventurer(conn, item["quest_row"], item["tid"]) is not None:
            blocked.append("{}/{}: held by an adventurer".format(item["quest"], item["tid"]))
            continue
        if item["epic"] is not None and item["deps"]:
            pending = []
            for dep_tid in item["deps"]:
                is_done, source, dep_disagreements = resolve.resolve_task_done(conn, project, item["epic"], dep_tid)
                if dep_disagreements:
                    disagreements.append(_disagreement_line(item["epic"], dep_tid, dep_disagreements))
                if not is_done:
                    pending.append("{} (per {})".format(dep_tid, source or "no source"))
            if pending:
                blocked.append("{}/{}: waiting on {}".format(item["quest"], item["tid"], ", ".join(pending)))
                continue
        ref = "task:{}/{}".format(item["quest"], item["tid"])
        ask_id = _open_ask_id_for_ref(conn, ref)
        if ask_id is not None:
            blocked.append("{}/{}: open ask #{}".format(item["quest"], item["tid"], ask_id))
            continue
        holder = _claim_holder(conn, now, project, claim_area(item), party)
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


def _drift_line(finding):
    return "update tracker/SDD: {}".format(finding)


def _render_all(candidates, drift, next_task, wait, offer, disagreements):
    lines = []
    for row, reason, _ in candidates:
        lines.append("PR {}: {}".format(_pr_label(row), reason))
    lines.extend(_drift_line(finding) for finding in drift)
    if next_task is not None:
        lines.append(
            "task {}/{}: {} — ready".format(next_task["quest"], next_task["tid"], _task_title_display(next_task))
        )
    if wait is not None:
        lines.append(wait)
    if offer is not None:
        lines.append(offer)
    for line in disagreements:
        lines.append("disagreement: {}".format(line))
    if not lines:
        lines.append("nothing actionable")
    return lines


def _render_single(ctx, candidates, drift, next_task, wait, offer, disagreements, blocked, acknowledge):
    if candidates:
        row, reason, should_ack = candidates[0]
        if should_ack and acknowledge:
            pr_commands.acknowledge_comments(ctx, row["repo"], row["number"])
        lines = ["PR {}: {}".format(_pr_label(row), reason)]
        for line in disagreements:
            lines.append("disagreement: {}".format(line))
        return lines
    if drift:
        lines = [_drift_line(drift[0])]
        for line in disagreements:
            lines.append("disagreement: {}".format(line))
        return lines
    if next_task is not None:
        lines = ["task {}/{}: {} — ready".format(next_task["quest"], next_task["tid"], _task_title_display(next_task))]
        for line in disagreements:
            lines.append("disagreement: {}".format(line))
        return lines
    if wait is not None:
        lines = [wait]
        for line in disagreements:
            lines.append("disagreement: {}".format(line))
        return lines
    if offer is not None:
        lines = [offer]
        for line in disagreements:
            lines.append("disagreement: {}".format(line))
        return lines
    lines = ["nothing actionable"]
    lines.extend(blocked)
    for line in disagreements:
        lines.append("disagreement: {}".format(line))
    return lines


def _paused_lines(paused_rows):
    return ["nothing actionable", "raid paused: {}".format(", ".join(row["raid"] for row in paused_rows))]


def _without(candidates, taken):
    return [candidate for candidate in candidates if (candidate[0]["repo"], candidate[0]["number"]) not in taken]


def _candidates(ctx, party, project):
    stale_hours = _stale_hours(ctx.projects_dir, project)
    tier0 = _tier0_candidates(ctx.conn, party)
    taken = {(row["repo"], row["number"]) for row, _, _ in tier0}
    tier1 = _without(_tier1_candidates(ctx.conn, party), taken)
    tier2 = _without(_tier2_candidates(ctx.conn, party), taken)
    tier3 = _without(_tier3_candidates(ctx.conn, ctx.now, party, stale_hours), taken)
    return tier0 + tier1 + tier2 + tier3


def _collect(ctx, party, project):
    candidates = _candidates(ctx, party, project)
    if project is None:
        return candidates, None, None, [], []
    next_task, disagreements, blocked = _evaluate_next_task(ctx.conn, ctx.now, project, party)
    if next_task is None:
        return candidates, None, None, disagreements, blocked
    wait = _cap_wait_line(ctx, party, project) or _wip_line(ctx, party)
    if wait is None:
        return candidates, next_task, None, disagreements, blocked
    return candidates, None, wait, disagreements, blocked


def has_work(ctx, binding):
    party = binding["party"]
    if raid_commands.paused_member_raids(ctx.conn, ctx.now, party):
        return False
    candidates, next_task, wait, _, _ = _collect(ctx, party, binding["project"])
    return bool(candidates or next_task is not None or wait is not None)


def next_task_item(ctx, binding):
    if raid_commands.paused_member_raids(ctx.conn, ctx.now, binding["party"]):
        return None
    return _collect(ctx, binding["party"], binding["project"])[1]


def _party_drift(ctx, party, project):
    if project is None:
        return []
    return drift_commands.party_findings(ctx.conn, project, party)


def run(ctx, binding, show_all, acknowledge):
    party, project = binding["party"], binding["project"]
    paused_rows = raid_commands.paused_member_raids(ctx.conn, ctx.now, party)
    if paused_rows:
        return _paused_lines(paused_rows)
    candidates, next_task, wait, disagreements, blocked = _collect(ctx, party, project)

    drift = _party_drift(ctx, party, project)
    offer = _open_quest_offer(ctx.conn, project, party)

    if show_all:
        return _render_all(candidates, drift, next_task, wait, offer, disagreements)
    return _render_single(ctx, candidates, drift, next_task, wait, offer, disagreements, blocked, acknowledge)
