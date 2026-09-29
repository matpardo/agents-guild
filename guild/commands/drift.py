from guild import session_info


def _epic_clause(alias, epic_filter):
    if epic_filter is None:
        return ""
    return " AND {}.epic = ?".format(alias)


def _epic_params(project, epic_filter):
    if epic_filter is None:
        return (project,)
    return (project, epic_filter)


def _rule_merged_pr_task_not_done(conn, project, epic_filter):
    rows = conn.execute(
        "SELECT prs.repo AS repo, prs.number AS number, prs.task_quest AS quest,"
        " prs.task_tid AS tid, quest_tasks.state AS state"
        " FROM prs"
        " JOIN quests ON quests.slug = prs.task_quest"
        " JOIN quest_tasks ON quest_tasks.quest = prs.task_quest AND quest_tasks.tid = prs.task_tid"
        " WHERE quests.project = ? AND prs.lifecycle = 'merged' AND quest_tasks.state != 'done'"
        + _epic_clause("quests", epic_filter),
        _epic_params(project, epic_filter),
    ).fetchall()
    return [
        "pr:{}#{}: merged, task:{}/{} state={}".format(
            row["repo"], row["number"], row["quest"], row["tid"], row["state"]
        )
        for row in rows
    ]


def _rule_tracker_sdd_disagree(conn, project, epic_filter):
    rows = conn.execute(
        "SELECT tasks.epic AS epic, tasks.tid AS tid, tasks.jira_key AS jira_key,"
        " tasks.sdd_status AS sdd_status, cards.status AS status,"
        " cards.status_category AS status_category"
        " FROM tasks"
        " JOIN cards ON cards.project = tasks.project AND cards.key = tasks.jira_key"
        " WHERE tasks.project = ?" + _epic_clause("tasks", epic_filter),
        _epic_params(project, epic_filter),
    ).fetchall()
    findings = []
    for row in rows:
        tracker_done = row["status_category"] == "done"
        sdd_done = row["sdd_status"] == "done"
        if tracker_done == sdd_done:
            continue
        findings.append(
            "task:{}/{} ({}): tracker={} ({}), sdd={}".format(
                row["epic"],
                row["tid"],
                row["jira_key"],
                "done" if tracker_done else "pending",
                row["status"],
                "done" if sdd_done else "pending",
            )
        )
    return findings


def _rule_sdd_task_without_card(conn, project, epic_filter):
    rows = conn.execute(
        "SELECT tasks.epic AS epic, tasks.tid AS tid, epics.jira_key AS epic_key"
        " FROM tasks"
        " JOIN epics ON epics.project = tasks.project AND epics.epic = tasks.epic"
        " WHERE tasks.project = ? AND epics.jira_key IS NOT NULL AND tasks.jira_key IS NULL"
        + _epic_clause("tasks", epic_filter),
        _epic_params(project, epic_filter),
    ).fetchall()
    return [
        "task:{}/{}: no tracker key (epic {} is keyed {})".format(
            row["epic"], row["tid"], row["epic"], row["epic_key"]
        )
        for row in rows
    ]


def _rule_card_not_under_epic(conn, project, epic_filter):
    rows = conn.execute(
        "SELECT tasks.epic AS epic, tasks.tid AS tid, tasks.jira_key AS jira_key,"
        " epics.jira_key AS epic_key"
        " FROM tasks"
        " JOIN epics ON epics.project = tasks.project AND epics.epic = tasks.epic"
        " JOIN cards ON cards.project = tasks.project AND cards.key = tasks.jira_key"
        " WHERE tasks.project = ? AND epics.jira_key IS NOT NULL AND cards.parent_key IS NULL"
        + _epic_clause("tasks", epic_filter),
        _epic_params(project, epic_filter),
    ).fetchall()
    return [
        "task:{}/{} ({}): card not under epic {} ({}) in tracker".format(
            row["epic"], row["tid"], row["jira_key"], row["epic"], row["epic_key"]
        )
        for row in rows
    ]


def _rule_pr_open_card_not_started(conn, project, epic_filter):
    rows = conn.execute(
        "SELECT prs.repo AS repo, prs.number AS number, prs.lifecycle AS lifecycle,"
        " quests.epic AS epic, prs.task_tid AS tid, tasks.jira_key AS jira_key,"
        " cards.status AS status"
        " FROM prs"
        " JOIN quests ON quests.slug = prs.task_quest"
        " JOIN tasks ON tasks.project = quests.project AND tasks.epic = quests.epic"
        " AND tasks.tid = prs.task_tid"
        " JOIN cards ON cards.project = tasks.project AND cards.key = tasks.jira_key"
        " WHERE quests.project = ? AND prs.lifecycle NOT IN ('merged', 'closed')"
        " AND cards.status_category = 'new'" + _epic_clause("quests", epic_filter),
        _epic_params(project, epic_filter),
    ).fetchall()
    return [
        "pr:{}#{} ({}): task:{}/{} card {} not started ({})".format(
            row["repo"], row["number"], row["lifecycle"], row["epic"], row["tid"],
            row["jira_key"], row["status"],
        )
        for row in rows
    ]


def _rule_pr_closed_unmerged(conn, project, epic_filter):
    rows = conn.execute(
        "SELECT prs.repo AS repo, prs.number AS number, prs.task_quest AS quest,"
        " prs.task_tid AS tid"
        " FROM prs"
        " JOIN quests ON quests.slug = prs.task_quest"
        " WHERE quests.project = ? AND prs.lifecycle = 'closed'" + _epic_clause("quests", epic_filter),
        _epic_params(project, epic_filter),
    ).fetchall()
    return [
        "pr:{}#{}: closed unmerged (task:{}/{})".format(row["repo"], row["number"], row["quest"], row["tid"])
        for row in rows
    ]


def _rule_party_without_leader(conn, project, sessions_dir):
    running_ids = session_info.running_session_ids(sessions_dir)
    rows = conn.execute(
        "SELECT name, leader_session_id FROM parties WHERE project = ? AND state = 'active'",
        (project,),
    ).fetchall()
    return [
        "party {}: leader session not running: resume or hand off".format(row["name"])
        for row in rows
        if row["leader_session_id"] not in running_ids
    ]


def _epic_done_task_findings(conn, project, epic):
    rows = conn.execute(
        "SELECT quest_tasks.quest AS quest, quest_tasks.tid AS tid, quest_tasks.state AS state"
        " FROM quest_tasks"
        " JOIN quests ON quests.slug = quest_tasks.quest"
        " WHERE quests.project = ? AND quests.epic = ? AND quest_tasks.state != 'done'",
        (project, epic),
    ).fetchall()
    return [
        "epic {} sdd_status=done but task:{}/{} state={}".format(epic, row["quest"], row["tid"], row["state"])
        for row in rows
    ]


def _epic_done_pr_findings(conn, project, epic):
    rows = conn.execute(
        "SELECT prs.repo AS repo, prs.number AS number, prs.lifecycle AS lifecycle"
        " FROM prs"
        " JOIN quests ON quests.slug = prs.task_quest"
        " WHERE quests.project = ? AND quests.epic = ? AND prs.lifecycle NOT IN ('merged', 'closed')",
        (project, epic),
    ).fetchall()
    return [
        "epic {} sdd_status=done but pr:{}#{} lifecycle={}".format(epic, row["repo"], row["number"], row["lifecycle"])
        for row in rows
    ]


def _rule_epic_done_with_open_work(conn, project, epic_filter):
    epic_rows = conn.execute(
        "SELECT epic FROM epics WHERE project = ? AND sdd_status = 'done'" + _epic_clause("epics", epic_filter),
        _epic_params(project, epic_filter),
    ).fetchall()
    findings = []
    for epic_row in epic_rows:
        epic = epic_row["epic"]
        findings.extend(_epic_done_task_findings(conn, project, epic))
        findings.extend(_epic_done_pr_findings(conn, project, epic))
    return findings


def _collect(conn, project, epic_filter, sessions_dir):
    return [
        ("merged PR, task not done", _rule_merged_pr_task_not_done(conn, project, epic_filter)),
        ("tracker and SDD disagree", _rule_tracker_sdd_disagree(conn, project, epic_filter)),
        ("SDD task without card", _rule_sdd_task_without_card(conn, project, epic_filter)),
        ("card not under its epic", _rule_card_not_under_epic(conn, project, epic_filter)),
        ("PR open, card not started", _rule_pr_open_card_not_started(conn, project, epic_filter)),
        ("PR closed unmerged", _rule_pr_closed_unmerged(conn, project, epic_filter)),
        ("party has no running leader", _rule_party_without_leader(conn, project, sessions_dir)),
        ("epic done with open work", _rule_epic_done_with_open_work(conn, project, epic_filter)),
    ]


def _render(groups):
    lines = []
    total = 0
    for name, findings in groups:
        if not findings:
            continue
        lines.append("{} ({})".format(name, len(findings)))
        lines.extend(findings)
        lines.append("")
        total += len(findings)
    if total == 0:
        lines.append("no drift")
    else:
        lines.append("{} findings".format(total))
    return lines


def run(ctx, project, epic_filter):
    groups = _collect(ctx.conn, project, epic_filter, ctx.sessions_dir)
    return _render(groups)
