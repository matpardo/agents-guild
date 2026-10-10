import json
from datetime import timedelta

from guild import config, events, merge_queue, resolve, sanitize, timeutil
from guild.commands import merge_queue as merge_queue_commands
from guild.commands import pr as pr_commands
from guild.commands import raid as raid_commands


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
        if (row["checks_failing"] or 0) > 0:
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


def _led_raid_members(conn, now, party):
    led = {}
    for membership in raid_commands.member_raids(conn, now, party):
        lead = raid_commands.active_lead(conn, now, membership["raid"])
        if lead is None or lead["party"] != party:
            continue
        led[membership["raid"]] = {
            row["party"] for row in raid_commands.active_members(conn, now, membership["raid"])
        } - {party}
    return led


def _raid_ask_lines(conn, raid_name, members):
    rows = conn.execute("SELECT * FROM asks WHERE state = 'open' ORDER BY id ASC").fetchall()
    return [
        'raid {}: ask #{} from {}: "{}"'.format(
            raid_name, row["id"], row["party"], sanitize.collapse_to_single_line(row["question"])
        )
        for row in rows
        if row["party"] in members
    ]


def _raid_queue_entry_line(raid_name, position, entry):
    prefix = "next action: " if entry["next_action"] else ""
    return "raid {}: merge queue {}{}. {} {} \u2014 {}".format(
        raid_name, prefix, position, entry["ref"], entry["party"], entry["action"]
    )


def _raid_queue_lines(conn, raid_name, members):
    scoped = merge_queue_commands.load_scoped_queue(conn, members)
    lines = [
        "raid {}: MAIN RED {} \u2192 fix before anything".format(raid_name, merge_queue_commands.main_label(row))
        for row in scoped["main"]
    ]
    lines.extend(
        _raid_queue_entry_line(raid_name, position, entry)
        for position, entry in enumerate(scoped["queue"], start=1)
    )
    return lines


def _lead_raid_lines(conn, now, party):
    led = _led_raid_members(conn, now, party)
    lines = []
    for raid_name in sorted(led):
        lines.extend(_raid_ask_lines(conn, raid_name, led[raid_name]))
    for raid_name in sorted(led):
        lines.extend(_raid_queue_lines(conn, raid_name, led[raid_name]))
    return [sanitize.strip_control_sequences(line) for line in lines]


def _pr_label(row):
    return "{}#{}".format(row["repo"], row["number"])


def _task_title_display(next_task):
    if next_task["epic"] is not None:
        return '"{}"'.format(next_task["title"])
    return next_task["title"]


def _render_all(candidates, next_task, disagreements, raid_lines):
    lines = []
    for row, reason, _ in candidates:
        lines.append("PR {}: {}".format(_pr_label(row), reason))
    if next_task is not None:
        lines.append(
            "task {}/{}: {} — ready".format(
                next_task["quest"], next_task["tid"], _task_title_display(next_task)
            )
        )
    for line in disagreements:
        lines.append("disagreement: {}".format(line))
    lines.extend(raid_lines)
    if not lines:
        lines.append("nothing actionable")
    return lines


def _render_single(ctx, candidates, next_task, disagreements, blocked, raid_lines, acknowledge):
    if candidates:
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
    if raid_lines:
        lines = [raid_lines[0]]
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
    return [
        candidate for candidate in candidates
        if (candidate[0]["repo"], candidate[0]["number"]) not in taken
    ]


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
        return candidates, None, [], []
    next_task, disagreements, blocked = _evaluate_next_task(ctx.conn, ctx.now, project, party)
    return candidates, next_task, disagreements, blocked


def has_work(ctx, binding):
    party = binding["party"]
    if raid_commands.paused_member_raids(ctx.conn, ctx.now, party):
        return False
    candidates, next_task, _, _ = _collect(ctx, party, binding["project"])
    return bool(candidates or next_task is not None)


def next_task_item(ctx, binding):
    if raid_commands.paused_member_raids(ctx.conn, ctx.now, binding["party"]):
        return None
    return _collect(ctx, binding["party"], binding["project"])[1]


def run(ctx, binding, show_all, acknowledge):
    party, project = binding["party"], binding["project"]
    paused_rows = raid_commands.paused_member_raids(ctx.conn, ctx.now, party)
    if paused_rows:
        return _paused_lines(paused_rows)
    candidates, next_task, disagreements, blocked = _collect(ctx, party, project)

    raid_lines = _lead_raid_lines(ctx.conn, ctx.now, party)

    if show_all:
        return _render_all(candidates, next_task, disagreements, raid_lines)
    return _render_single(ctx, candidates, next_task, disagreements, blocked, raid_lines, acknowledge)
