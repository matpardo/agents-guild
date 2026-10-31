from guild import raid_members, work_queue
from guild.commands import drift as drift_commands
from guild.commands import pr as pr_commands


def _open_quest_offer(conn, project, party):
    if project is None or work_queue.queued_tasks(conn, project, party):
        return None
    row = conn.execute(
        "SELECT slug FROM quests WHERE project = ? AND party IS NULL AND state = 'active' ORDER BY rowid ASC",
        (project,),
    ).fetchone()
    if row is None:
        return None
    return "take open quest {}".format(row["slug"])


def _task_title_display(next_task):
    if next_task["epic"] is not None:
        return '"{}"'.format(next_task["title"])
    return next_task["title"]


def _drift_line(finding):
    return "update tracker/SDD: {}".format(finding)


def _render_all(candidates, drift, next_task, wait, offer, disagreements):
    lines = []
    for row, reason, _ in candidates:
        lines.append("PR {}: {}".format(work_queue.pr_label(row), reason))
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
        lines = ["PR {}: {}".format(work_queue.pr_label(row), reason)]
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


def _party_drift(ctx, party, project):
    if project is None:
        return []
    return drift_commands.party_findings(ctx.conn, project, party)


def run(ctx, binding, show_all, acknowledge):
    party, project = binding["party"], binding["project"]
    paused_rows = raid_members.paused_member_raids(ctx.conn, ctx.now, party)
    if paused_rows:
        return _paused_lines(paused_rows)
    candidates, next_task, wait, disagreements, blocked = work_queue.collect(ctx, party, project)

    drift = _party_drift(ctx, party, project)
    offer = _open_quest_offer(ctx.conn, project, party)

    if show_all:
        return _render_all(candidates, drift, next_task, wait, offer, disagreements)
    return _render_single(ctx, candidates, drift, next_task, wait, offer, disagreements, blocked, acknowledge)
