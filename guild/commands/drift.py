from guild import session_info

_DEFAULT_PARTY_STATES = ("active", "awaiting-leader")


def _epic_clause(alias, epics):
    if epics is None:
        return ""
    if not epics:
        return " AND 0"
    placeholders = ", ".join("?" for _ in epics)
    return " AND {}.epic IN ({})".format(alias, placeholders)


def _epic_params(project, epics):
    if epics is None:
        return (project,)
    return (project,) + tuple(epics)


def _party_clause(party_states):
    if party_states is None:
        return ""
    placeholders = ", ".join("?" for _ in party_states)
    return " AND parties.state IN ({})".format(placeholders)


def _party_params(party_states):
    if party_states is None:
        return ()
    return tuple(party_states)


def _active_quest_epics(conn, project):
    rows = conn.execute(
        "SELECT DISTINCT epic FROM quests"
        " WHERE project = ? AND state = 'active' AND epic IS NOT NULL"
        " ORDER BY epic",
        (project,),
    ).fetchall()
    return [row["epic"] for row in rows]


def _rule_merged_pr_task_not_done(conn, project, epics, party_states):
    rows = conn.execute(
        "SELECT prs.repo AS repo, prs.number AS number, prs.task_quest AS quest,"
        " prs.task_tid AS tid, quest_tasks.state AS state"
        " FROM prs"
        " JOIN quests ON quests.slug = prs.task_quest"
        " JOIN quest_tasks ON quest_tasks.quest = prs.task_quest AND quest_tasks.tid = prs.task_tid"
        " JOIN parties ON parties.name = prs.party"
        " WHERE quests.project = ? AND prs.lifecycle = 'merged' AND quest_tasks.state != 'done'"
        + _epic_clause("quests", epics) + _party_clause(party_states),
        _epic_params(project, epics) + _party_params(party_states),
    ).fetchall()
    return [
        "pr:{}#{}: merged, task:{}/{} state={}".format(
            row["repo"], row["number"], row["quest"], row["tid"], row["state"]
        )
        for row in rows
    ]


def _rule_tracker_sdd_disagree(conn, project, epics):
    rows = conn.execute(
        "SELECT tasks.epic AS epic, tasks.tid AS tid, tasks.jira_key AS jira_key,"
        " tasks.sdd_status AS sdd_status, cards.status AS status,"
        " cards.status_category AS status_category"
        " FROM tasks"
        " JOIN cards ON cards.project = tasks.project AND cards.key = tasks.jira_key"
        " WHERE tasks.project = ?" + _epic_clause("tasks", epics),
        _epic_params(project, epics),
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


def _rule_sdd_task_without_card(conn, project, epics):
    rows = conn.execute(
        "SELECT tasks.epic AS epic, tasks.tid AS tid, epics.jira_key AS epic_key"
        " FROM tasks"
        " JOIN epics ON epics.project = tasks.project AND epics.epic = tasks.epic"
        " WHERE tasks.project = ? AND epics.jira_key IS NOT NULL AND tasks.jira_key IS NULL"
        + _epic_clause("tasks", epics),
        _epic_params(project, epics),
    ).fetchall()
    return [
        "task:{}/{}: no tracker key (epic {} is keyed {})".format(
            row["epic"], row["tid"], row["epic"], row["epic_key"]
        )
        for row in rows
    ]


def _rule_card_not_under_epic(conn, project, epics):
    rows = conn.execute(
        "SELECT tasks.epic AS epic, tasks.tid AS tid, tasks.jira_key AS jira_key,"
        " epics.jira_key AS epic_key"
        " FROM tasks"
        " JOIN epics ON epics.project = tasks.project AND epics.epic = tasks.epic"
        " JOIN cards ON cards.project = tasks.project AND cards.key = tasks.jira_key"
        " WHERE tasks.project = ? AND epics.jira_key IS NOT NULL AND cards.parent_key IS NULL"
        + _epic_clause("tasks", epics),
        _epic_params(project, epics),
    ).fetchall()
    return [
        "task:{}/{} ({}): card not under epic {} ({}) in tracker".format(
            row["epic"], row["tid"], row["jira_key"], row["epic"], row["epic_key"]
        )
        for row in rows
    ]


def _rule_pr_open_card_not_started(conn, project, epics, party_states):
    rows = conn.execute(
        "SELECT prs.repo AS repo, prs.number AS number, prs.lifecycle AS lifecycle,"
        " quests.epic AS epic, prs.task_tid AS tid, tasks.jira_key AS jira_key,"
        " cards.status AS status"
        " FROM prs"
        " JOIN quests ON quests.slug = prs.task_quest"
        " JOIN tasks ON tasks.project = quests.project AND tasks.epic = quests.epic"
        " AND tasks.tid = prs.task_tid"
        " JOIN cards ON cards.project = tasks.project AND cards.key = tasks.jira_key"
        " JOIN parties ON parties.name = prs.party"
        " WHERE quests.project = ? AND prs.lifecycle NOT IN ('merged', 'closed')"
        " AND cards.status_category = 'new'"
        + _epic_clause("quests", epics) + _party_clause(party_states),
        _epic_params(project, epics) + _party_params(party_states),
    ).fetchall()
    return [
        "pr:{}#{} ({}): task:{}/{} card {} not started ({})".format(
            row["repo"], row["number"], row["lifecycle"], row["epic"], row["tid"],
            row["jira_key"], row["status"],
        )
        for row in rows
    ]


def _rule_pr_closed_unmerged(conn, project, epics, party_states):
    rows = conn.execute(
        "SELECT prs.repo AS repo, prs.number AS number, prs.task_quest AS quest,"
        " prs.task_tid AS tid"
        " FROM prs"
        " JOIN quests ON quests.slug = prs.task_quest"
        " JOIN parties ON parties.name = prs.party"
        " WHERE quests.project = ? AND prs.lifecycle = 'closed'"
        + _epic_clause("quests", epics) + _party_clause(party_states),
        _epic_params(project, epics) + _party_params(party_states),
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


def _rule_epic_done_with_open_work(conn, project, epics):
    epic_rows = conn.execute(
        "SELECT epic FROM epics WHERE project = ? AND sdd_status = 'done'" + _epic_clause("epics", epics),
        _epic_params(project, epics),
    ).fetchall()
    findings = []
    for epic_row in epic_rows:
        epic = epic_row["epic"]
        findings.extend(_epic_done_task_findings(conn, project, epic))
        findings.extend(_epic_done_pr_findings(conn, project, epic))
    return findings


def _rule_quest_task_not_in_sdd(conn, project, epics, party_states):
    rows = conn.execute(
        "SELECT quests.epic AS epic, quest_tasks.quest AS quest, quest_tasks.tid AS tid"
        " FROM quest_tasks"
        " JOIN quests ON quests.slug = quest_tasks.quest"
        " JOIN parties ON parties.name = quests.party"
        " WHERE quests.project = ? AND quests.epic IS NOT NULL"
        " AND NOT EXISTS (SELECT 1 FROM tasks WHERE tasks.project = quests.project"
        " AND tasks.epic = quests.epic AND tasks.tid = quest_tasks.tid)"
        + _epic_clause("quests", epics) + _party_clause(party_states)
        + " ORDER BY quests.epic, quest_tasks.quest, quest_tasks.tid",
        _epic_params(project, epics) + _party_params(party_states),
    ).fetchall()
    return [
        "task:{}/{}: not in epic {} tasks.md, add it".format(row["quest"], row["tid"], row["epic"])
        for row in rows
    ]


def _rule_task_done_sdd_not_done(conn, project, epics, party_states):
    rows = conn.execute(
        "SELECT quests.epic AS epic, quest_tasks.quest AS quest, quest_tasks.tid AS tid,"
        " tasks.sdd_status AS sdd_status"
        " FROM quest_tasks"
        " JOIN quests ON quests.slug = quest_tasks.quest"
        " JOIN tasks ON tasks.project = quests.project AND tasks.epic = quests.epic"
        " AND tasks.tid = quest_tasks.tid"
        " JOIN parties ON parties.name = quests.party"
        " WHERE quests.project = ? AND quest_tasks.state = 'done' AND tasks.sdd_status != 'done'"
        + _epic_clause("quests", epics) + _party_clause(party_states)
        + " ORDER BY quests.epic, quest_tasks.quest, quest_tasks.tid",
        _epic_params(project, epics) + _party_params(party_states),
    ).fetchall()
    return [
        "task:{}/{} done, epic {} tasks.md says {}".format(
            row["quest"], row["tid"], row["epic"], row["sdd_status"]
        )
        for row in rows
    ]


def _collect_epic_scoped(conn, project, epics, party_states):
    return [
        ("merged PR, task not done", _rule_merged_pr_task_not_done(conn, project, epics, party_states)),
        ("tracker and SDD disagree", _rule_tracker_sdd_disagree(conn, project, epics)),
        ("SDD task without card", _rule_sdd_task_without_card(conn, project, epics)),
        ("card not under its epic", _rule_card_not_under_epic(conn, project, epics)),
        ("PR open, card not started", _rule_pr_open_card_not_started(conn, project, epics, party_states)),
        ("PR closed unmerged", _rule_pr_closed_unmerged(conn, project, epics, party_states)),
        ("epic done with open work", _rule_epic_done_with_open_work(conn, project, epics)),
        ("quest task not in SDD", _rule_quest_task_not_in_sdd(conn, project, epics, party_states)),
        ("task done, SDD not done", _rule_task_done_sdd_not_done(conn, project, epics, party_states)),
    ]


def _collect(conn, project, epics, party_states, sessions_dir):
    groups = _collect_epic_scoped(conn, project, epics, party_states)
    groups.insert(6, ("party has no running leader", _rule_party_without_leader(conn, project, sessions_dir)))
    return groups


def epic_findings(conn, project, epic):
    groups = _collect_epic_scoped(conn, project, (epic,), None)
    return [finding for _, rule_findings in groups for finding in rule_findings]


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


def board_findings(ctx, project):
    epics, party_states, scope_line = _resolve_scope(ctx.conn, project, None, False)
    groups = _collect(ctx.conn, project, epics, party_states, ctx.sessions_dir)
    findings = {name: rule_findings for name, rule_findings in groups if rule_findings}
    return {"project": project, "scope": scope_line, "findings": findings}


def _resolve_scope(conn, project, epic, all_scope):
    if all_scope:
        return None, None, "scope: whole project"
    if epic is not None:
        return (epic,), None, "scope: epic {}".format(epic)
    epics = _active_quest_epics(conn, project)
    if not epics:
        return [], _DEFAULT_PARTY_STATES, "scope: no epics in active quests"
    return (
        epics,
        _DEFAULT_PARTY_STATES,
        "scope: {} epics in active quests (use --all for the whole project)".format(len(epics)),
    )


def run(ctx, project, epic, all_scope):
    epics, party_states, scope_line = _resolve_scope(ctx.conn, project, epic, all_scope)
    groups = _collect(ctx.conn, project, epics, party_states, ctx.sessions_dir)
    return [scope_line] + _render(groups)
