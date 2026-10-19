import re

from guild import session_info

_DEFAULT_PARTY_SCOPE = ("state", ("active", "awaiting-leader"))


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


def _party_clause(party_scope):
    if party_scope is None:
        return ""
    column, values = party_scope
    placeholders = ", ".join("?" for _ in values)
    return " AND parties.{} IN ({})".format(column, placeholders)


def _party_params(party_scope):
    if party_scope is None:
        return ()
    return tuple(party_scope[1])


def _active_quest_epics(conn, project):
    rows = conn.execute(
        "SELECT DISTINCT epic FROM quests"
        " WHERE project = ? AND state = 'active' AND epic IS NOT NULL"
        " ORDER BY epic",
        (project,),
    ).fetchall()
    return [row["epic"] for row in rows]


def _rule_merged_pr_task_not_done(conn, project, epics, party_scope):
    rows = conn.execute(
        "SELECT prs.repo AS repo, prs.number AS number, prs.task_quest AS quest,"
        " prs.task_tid AS tid, quest_tasks.state AS state"
        " FROM prs"
        " JOIN quests ON quests.slug = prs.task_quest"
        " JOIN quest_tasks ON quest_tasks.quest = prs.task_quest AND quest_tasks.tid = prs.task_tid"
        " JOIN parties ON parties.name = prs.party"
        " WHERE quests.project = ? AND prs.lifecycle = 'merged' AND quest_tasks.state != 'done'"
        + _epic_clause("quests", epics) + _party_clause(party_scope),
        _epic_params(project, epics) + _party_params(party_scope),
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


_PR_CARD_COLUMNS = (
    "SELECT prs.repo AS repo, prs.number AS number, prs.lifecycle AS lifecycle,"
    " quests.epic AS epic, prs.task_tid AS tid, cards.key AS card_key,"
    " cards.status AS status, cards.status_category AS status_category"
)


def _card_link_scope_clause(epics, party_scope):
    if epics is None or party_scope is not None:
        return ""
    return " AND 0"


def _pr_card_findings(conn, project, epics, party_scope, lifecycle_condition, card_condition, render):
    task_link = (
        _PR_CARD_COLUMNS
        + " FROM prs"
        " JOIN quests ON quests.slug = prs.task_quest"
        " JOIN tasks ON tasks.project = quests.project AND tasks.epic = quests.epic"
        " AND tasks.tid = prs.task_tid"
        " JOIN cards ON cards.project = tasks.project AND cards.key = tasks.jira_key"
        " JOIN parties ON parties.name = prs.party"
        " WHERE quests.project = ? AND " + lifecycle_condition + " AND " + card_condition
        + _epic_clause("quests", epics) + _party_clause(party_scope)
    )
    card_link = (
        _PR_CARD_COLUMNS.replace("quests.epic", "NULL")
        + " FROM prs"
        " JOIN parties ON parties.name = prs.party"
        " JOIN cards ON cards.project = parties.project AND cards.key = prs.card"
        " WHERE parties.project = ? AND " + lifecycle_condition + " AND " + card_condition
        + _card_link_scope_clause(epics, party_scope) + _party_clause(party_scope)
    )
    params = (
        _epic_params(project, epics) + _party_params(party_scope)
        + (project,) + _party_params(party_scope)
    )
    rows = conn.execute(task_link + " UNION ALL " + card_link, params).fetchall()
    return [render(row) for row in rows]


def _pr_task_ref(row):
    if row["tid"] is None:
        return ""
    return "task:{}/{} ".format(row["epic"], row["tid"])


def _rule_pr_open_card_not_started(conn, project, epics, party_scope):
    return _pr_card_findings(
        conn, project, epics, party_scope,
        "prs.lifecycle NOT IN ('merged', 'closed')", "cards.status_category = 'new'",
        lambda row: "pr:{}#{} ({}): {}card {} not started ({}): move {} to In Progress".format(
            row["repo"], row["number"], row["lifecycle"], _pr_task_ref(row),
            row["card_key"], row["status"], row["card_key"],
        ),
    )


def _rule_pr_merged_card_not_done(conn, project, epics, party_scope):
    rows = _pr_card_findings(
        conn, project, epics, party_scope,
        "prs.lifecycle = 'merged'", "cards.status_category != 'done'",
        lambda row: row,
    )
    by_card = {}
    for row in sorted(rows, key=lambda row: (row["card_key"], row["repo"], row["number"])):
        by_card.setdefault(row["card_key"], []).append(row)
    return [
        "card {} not done ({}): move {} to Done; merged {}".format(
            key, card_rows[0]["status"], key,
            ", ".join(
                "pr:{}#{} {}".format(row["repo"], row["number"], _pr_task_ref(row)).strip()
                for row in card_rows
            ),
        )
        for key, card_rows in by_card.items()
    ]


def _rule_task_started_card_not_started(conn, project, epics, party_scope):
    rows = conn.execute(
        "SELECT quests.epic AS epic, quest_tasks.quest AS quest, quest_tasks.tid AS tid,"
        " tasks.jira_key AS jira_key, cards.status AS status"
        " FROM quest_tasks"
        " JOIN quests ON quests.slug = quest_tasks.quest"
        " JOIN tasks ON tasks.project = quests.project AND tasks.epic = quests.epic"
        " AND tasks.tid = quest_tasks.tid"
        " JOIN cards ON cards.project = tasks.project AND cards.key = tasks.jira_key"
        " JOIN parties ON parties.name = quests.party"
        " WHERE quests.project = ? AND quest_tasks.state = 'active' AND cards.status_category = 'new'"
        + _epic_clause("quests", epics) + _party_clause(party_scope)
        + " ORDER BY quests.epic, quest_tasks.quest, quest_tasks.tid",
        _epic_params(project, epics) + _party_params(party_scope),
    ).fetchall()
    return [
        "task:{}/{} started, card {} not started ({}): move {} to In Progress".format(
            row["quest"], row["tid"], row["jira_key"], row["status"], row["jira_key"]
        )
        for row in rows
    ]


def _rule_pr_closed_unmerged(conn, project, epics, party_scope):
    rows = conn.execute(
        "SELECT prs.repo AS repo, prs.number AS number, prs.task_quest AS quest,"
        " prs.task_tid AS tid"
        " FROM prs"
        " JOIN quests ON quests.slug = prs.task_quest"
        " JOIN parties ON parties.name = prs.party"
        " WHERE quests.project = ? AND prs.lifecycle = 'closed'"
        + _epic_clause("quests", epics) + _party_clause(party_scope),
        _epic_params(project, epics) + _party_params(party_scope),
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


def _rule_quest_task_not_in_sdd(conn, project, epics, party_scope):
    rows = conn.execute(
        "SELECT quests.epic AS epic, quest_tasks.quest AS quest, quest_tasks.tid AS tid"
        " FROM quest_tasks"
        " JOIN quests ON quests.slug = quest_tasks.quest"
        " JOIN parties ON parties.name = quests.party"
        " WHERE quests.project = ? AND quests.epic IS NOT NULL"
        " AND NOT EXISTS (SELECT 1 FROM tasks WHERE tasks.project = quests.project"
        " AND tasks.epic = quests.epic AND tasks.tid = quest_tasks.tid)"
        + _epic_clause("quests", epics) + _party_clause(party_scope)
        + " ORDER BY quests.epic, quest_tasks.quest, quest_tasks.tid",
        _epic_params(project, epics) + _party_params(party_scope),
    ).fetchall()
    return [
        "task:{}/{}: not in epic {} tasks.md, add it".format(row["quest"], row["tid"], row["epic"])
        for row in rows
    ]


def _rule_task_done_sdd_not_done(conn, project, epics, party_scope):
    rows = conn.execute(
        "SELECT quests.epic AS epic, quest_tasks.quest AS quest, quest_tasks.tid AS tid,"
        " tasks.sdd_status AS sdd_status"
        " FROM quest_tasks"
        " JOIN quests ON quests.slug = quest_tasks.quest"
        " JOIN tasks ON tasks.project = quests.project AND tasks.epic = quests.epic"
        " AND tasks.tid = quest_tasks.tid"
        " JOIN parties ON parties.name = quests.party"
        " WHERE quests.project = ? AND quest_tasks.state = 'done' AND tasks.sdd_status != 'done'"
        + _epic_clause("quests", epics) + _party_clause(party_scope)
        + " ORDER BY quests.epic, quest_tasks.quest, quest_tasks.tid",
        _epic_params(project, epics) + _party_params(party_scope),
    ).fetchall()
    return [
        "task:{}/{} done, epic {} tasks.md says {}".format(
            row["quest"], row["tid"], row["epic"], row["sdd_status"]
        )
        for row in rows
    ]


def _collect_epic_scoped(conn, project, epics, party_scope):
    return [
        ("merged PR, task not done", _rule_merged_pr_task_not_done(conn, project, epics, party_scope)),
        ("tracker and SDD disagree", _rule_tracker_sdd_disagree(conn, project, epics)),
        ("SDD task without card", _rule_sdd_task_without_card(conn, project, epics)),
        ("card not under its epic", _rule_card_not_under_epic(conn, project, epics)),
        ("PR open, card not started", _rule_pr_open_card_not_started(conn, project, epics, party_scope)),
        ("PR merged, card not done", _rule_pr_merged_card_not_done(conn, project, epics, party_scope)),
        ("task started, card not started", _rule_task_started_card_not_started(conn, project, epics, party_scope)),
        ("PR closed unmerged", _rule_pr_closed_unmerged(conn, project, epics, party_scope)),
        ("epic done with open work", _rule_epic_done_with_open_work(conn, project, epics)),
        ("quest task not in SDD", _rule_quest_task_not_in_sdd(conn, project, epics, party_scope)),
        ("task done, SDD not done", _rule_task_done_sdd_not_done(conn, project, epics, party_scope)),
    ]


def _collect(conn, project, epics, party_scope, sessions_dir):
    groups = _collect_epic_scoped(conn, project, epics, party_scope)
    groups.insert(8, ("party has no running leader", _rule_party_without_leader(conn, project, sessions_dir)))
    return groups


def epic_findings(conn, project, epic):
    groups = _collect_epic_scoped(conn, project, (epic,), None)
    return [finding for _, rule_findings in groups for finding in rule_findings]


def epic_findings_by_owner(conn, project, epic, party):
    own = []
    foreign = []
    for rule, rule_findings in _collect_epic_scoped(conn, project, (epic,), None):
        for text in rule_findings:
            owner = _finding_party(conn, rule, text)
            if owner is None or owner == party:
                own.append(text)
                continue
            foreign.append({"text": text, "party": owner})
    return {"own": own, "foreign": foreign}


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


def party_findings(conn, project, party):
    party_scope = ("name", (party,))
    rules = (
        _rule_pr_open_card_not_started,
        _rule_pr_merged_card_not_done,
        _rule_task_started_card_not_started,
        _rule_task_done_sdd_not_done,
    )
    return [finding for rule in rules for finding in rule(conn, project, None, party_scope)]


def started_card_to_move(conn, quest, tid):
    row = conn.execute(
        "SELECT tasks.jira_key AS jira_key FROM quests"
        " JOIN tasks ON tasks.project = quests.project AND tasks.epic = quests.epic AND tasks.tid = ?"
        " JOIN cards ON cards.project = tasks.project AND cards.key = tasks.jira_key"
        " WHERE quests.slug = ? AND cards.status_category = 'new'",
        (tid, quest),
    ).fetchone()
    if row is None:
        return None
    return row["jira_key"]


def _merged_task_link(conn, pr):
    if pr["task_quest"] is None:
        return pr["card"], None, None
    row = conn.execute(
        "SELECT quests.epic AS epic, tasks.jira_key AS jira_key, tasks.sdd_status AS sdd_status"
        " FROM quests JOIN tasks ON tasks.project = quests.project AND tasks.epic = quests.epic"
        " AND tasks.tid = ? WHERE quests.slug = ?",
        (pr["task_tid"], pr["task_quest"]),
    ).fetchone()
    if row is None:
        return None, None, None
    return row["jira_key"], row["epic"], row["sdd_status"]


def _card_open(conn, party, key):
    return conn.execute(
        "SELECT 1 FROM cards JOIN parties ON parties.project = cards.project"
        " WHERE parties.name = ? AND cards.key = ? AND cards.status_category != 'done'",
        (party, key),
    ).fetchone() is not None


def merged_pr_moves(conn, pr):
    key, epic, sdd_status = _merged_task_link(conn, pr)
    moves = []
    if key is not None and _card_open(conn, pr["party"], key):
        moves.append("move {} to Done".format(key))
    if epic is not None and sdd_status != "done":
        moves.append("mark {} done in {} tasks.md".format(pr["task_tid"], epic))
    return moves


_PARTY_OWNED_RULES = frozenset((
    "merged PR, task not done",
    "PR open, card not started",
    "PR merged, card not done",
    "task started, card not started",
    "PR closed unmerged",
    "quest task not in SDD",
    "task done, SDD not done",
))
_PR_REF = re.compile(r"pr:(\S+)#(\d+)")
_TASK_REF = re.compile(r"task:([^/\s]+)/")


def _finding_party(conn, rule, text):
    if rule not in _PARTY_OWNED_RULES:
        return None
    pr_ref = _PR_REF.search(text)
    if pr_ref is not None:
        row = conn.execute(
            "SELECT party FROM prs WHERE repo = ? AND number = ?", (pr_ref.group(1), int(pr_ref.group(2)))
        ).fetchone()
        return None if row is None else row["party"]
    task_ref = _TASK_REF.search(text)
    if task_ref is None:
        return None
    row = conn.execute("SELECT party FROM quests WHERE slug = ?", (task_ref.group(1),)).fetchone()
    return None if row is None else row["party"]


def board_findings(ctx, project):
    epics, party_scope, scope_line = _resolve_scope(ctx.conn, project, None, False)
    groups = _collect(ctx.conn, project, epics, party_scope, ctx.sessions_dir)
    findings = {
        name: [{"text": text, "party": _finding_party(ctx.conn, name, text)} for text in rule_findings]
        for name, rule_findings in groups
        if rule_findings
    }
    return {"project": project, "scope": scope_line, "findings": findings}


def _resolve_scope(conn, project, epic, all_scope):
    if all_scope:
        return None, None, "scope: whole project"
    if epic is not None:
        return (epic,), None, "scope: epic {}".format(epic)
    epics = _active_quest_epics(conn, project)
    if not epics:
        return [], _DEFAULT_PARTY_SCOPE, "scope: no epics in active quests"
    return (
        epics,
        _DEFAULT_PARTY_SCOPE,
        "scope: {} epics in active quests (use --all for the whole project)".format(len(epics)),
    )


def run(ctx, project, epic, all_scope):
    epics, party_scope, scope_line = _resolve_scope(ctx.conn, project, epic, all_scope)
    groups = _collect(ctx.conn, project, epics, party_scope, ctx.sessions_dir)
    return [scope_line] + _render(groups)
