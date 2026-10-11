from pathlib import Path

from guild import merge_queue, paths, pr_asks, resume, session_info, timeutil, transcript_usage
from guild.adapters import sdd
from guild.commands import merge_queue as merge_queue_commands
from guild.commands import next as next_commands
from guild.commands import revive


_RESUME_GRACE_SECONDS = 60
_RESUME_TEXT = "continue"
_SDD_PROGRESS_SECONDS = 24 * 3600
_CHECKED_LIFECYCLES = ("draft", "converging", "ready")
_REASON_SLUGS = (
    ("merge conflict", "conflict"),
    ("changes requested", "changes_requested"),
    ("unresolved", "unresolved_threads"),
    ("behind base", "behind"),
)


class Trigger:
    def __init__(self, project, rule, key, party, subject, prompt):
        self.project = project
        self.rule = rule
        self.key = key
        self.party = party
        self.subject = subject
        self.prompt = prompt


class PromoteTrigger(Trigger):
    def __init__(self, project, key, party, repo, number, needs_human_review):
        subject = "{}#{}".format(repo, number)
        verdict = "converged; needs human review before ready" if needs_human_review else "promoted to ready"
        super().__init__(project, "pr_promote", key, party, subject, "{} {}".format(subject, verdict))
        self.repo = repo
        self.number = number
        self.needs_human_review = needs_human_review


def _ask_trigger(project, party, ask_id):
    prompt = "{} Dispatched: ask #{} was answered; read guild asks {}.".format(
        resume.RESUME_PROMPT, ask_id, ask_id
    )
    return Trigger(project, "ask_answered", "ask_answered:{}".format(ask_id), party, "ask #{}".format(ask_id), prompt)


def _checks_trigger(project, party, repo, number, head_sha):
    subject = "{}#{}".format(repo, number)
    prompt = "{} Dispatched: checks fail on {}; run gh pr checks {} --repo {}.".format(
        resume.RESUME_PROMPT, subject, number, repo
    )
    key = "checks_failing:{}:{}".format(subject, head_sha)
    return Trigger(project, "checks_failing", key, party, subject, prompt)


def _unmergeable_trigger(project, party, repo, number, head_sha, slugs):
    subject = "{}#{}".format(repo, number)
    reasons = ", ".join(slug.replace("_", " ") for slug in slugs)
    prompt = "{} Dispatched: {} is not mergeable ({}); run gh pr view {} --repo {} and resolve review threads.".format(
        resume.RESUME_PROMPT, subject, reasons, number, repo
    )
    key = "pr_unmergeable:{}:{}:{}".format(subject, head_sha, ",".join(slugs))
    return Trigger(project, "pr_unmergeable", key, party, subject, prompt)


def _unmergeable_slugs(pr):
    reasons = merge_queue.review_reasons(
        pr["mergeable"], pr["review_decision"], pr["unresolved_threads"], pr["merge_state"]
    )
    return sorted(slug for reason in reasons for prefix, slug in _REASON_SLUGS if prefix in reason)


def _owner(conn, projects, repo, number):
    owner = conn.execute(
        "SELECT prs.party AS party, parties.project AS project, prs.mergeable AS mergeable,"
        " prs.review_decision AS review_decision, prs.unresolved_threads AS unresolved_threads,"
        " prs.merge_state AS merge_state, prs.blocked_external AS blocked_external, prs.needs_ask_answer AS needs_ask_answer, prs.needs_human_pr_review AS needs_human_pr_review, "
        + pr_asks.OPEN_ASK_ID_SQL
        + " FROM prs"
        " JOIN parties ON parties.name = prs.party WHERE prs.repo = ? AND prs.number = ? AND prs.seeded = 0",
        (repo, number),
    ).fetchone()
    if owner is None or owner["project"] not in projects:
        return None
    if repo not in projects[owner["project"]]["github"]["repos"]:
        return None
    return owner


def _ask_answered(conn, projects, event):
    if event["kind"] != "ask.answered":
        return None
    ask_id = event["payload"]["id"]
    ask = conn.execute(
        "SELECT asks.party AS party, parties.project AS project FROM asks"
        " JOIN parties ON parties.name = asks.party WHERE asks.id = ? AND asks.state = 'answered'",
        (ask_id,),
    ).fetchone()
    if ask is None or ask["project"] is None:
        return None
    return _ask_trigger(ask["project"], ask["party"], ask_id)


def _checks_failing(conn, projects, event):
    if event["kind"] != "pr.synced":
        return None
    payload = event["payload"]
    if payload["lifecycle"] not in _CHECKED_LIFECYCLES:
        return None
    if payload["checks_failing"] <= 0 or payload.get("checks_pending") != 0 or not payload.get("head_sha"):
        return None
    if payload.get("cross_repository") is True:
        return None
    repo, number = payload["repo"], payload["number"]
    owner = _owner(conn, projects, repo, number)
    if owner is None:
        return None
    return _checks_trigger(owner["project"], owner["party"], repo, number, payload["head_sha"])


def _pr_unmergeable(conn, projects, event):
    if event["kind"] != "pr.synced":
        return None
    payload = event["payload"]
    if payload["lifecycle"] not in _CHECKED_LIFECYCLES or not payload.get("head_sha"):
        return None
    if payload.get("cross_repository") is True:
        return None
    repo, number = payload["repo"], payload["number"]
    owner = _owner(conn, projects, repo, number)
    if owner is None:
        return None
    if owner["blocked_external"] is not None:
        return None
    slugs = _unmergeable_slugs(owner)
    if not slugs:
        return None
    return _unmergeable_trigger(owner["project"], owner["party"], repo, number, payload["head_sha"], slugs)


def _pr_promote(conn, projects, event):
    if event["kind"] != "pr.synced":
        return None
    payload = event["payload"]
    if payload["lifecycle"] != "converging" or payload.get("gh_draft") is not True or not payload.get("head_sha"):
        return None
    if payload["checks_failing"] != 0 or payload.get("checks_pending") != 0 or payload["checks_passing"] <= 0:
        return None
    if payload.get("cross_repository") is True:
        return None
    repo, number = payload["repo"], payload["number"]
    owner = _owner(conn, projects, repo, number)
    if owner is None or owner["blocked_external"] is not None or pr_asks.needs_answer(owner):
        return None
    if _unmergeable_slugs(owner):
        return None
    key = "pr_promote:{}#{}:{}".format(repo, number, payload["head_sha"])
    return PromoteTrigger(
        owner["project"], key, owner["party"], repo, number, bool(owner["needs_human_pr_review"])
    )


def _deferred_ask(conn, row):
    ask_id = int(row["key"].split(":", 1)[1])
    answered = conn.execute("SELECT 1 FROM asks WHERE id = ? AND state = 'answered'", (ask_id,)).fetchone()
    if answered is None:
        return None
    return _ask_trigger(row["project"], row["party"], ask_id)


def _deferred_checks(conn, row):
    subject, head_sha = row["key"].split(":", 1)[1].rsplit(":", 1)
    repo, number = subject.rsplit("#", 1)
    pr = conn.execute(
        "SELECT lifecycle, checks_failing, checks_pending FROM prs WHERE repo = ? AND number = ? AND seeded = 0",
        (repo, int(number)),
    ).fetchone()
    if pr is None or pr["lifecycle"] not in _CHECKED_LIFECYCLES:
        return None
    if not pr["checks_failing"] or pr["checks_pending"] != 0:
        return None
    return _checks_trigger(row["project"], row["party"], repo, int(number), head_sha)


def _deferred_unmergeable(conn, row):
    subject, head_sha, slug_list = row["key"].split(":", 1)[1].split(":", 2)
    repo, number = subject.rsplit("#", 1)
    pr = conn.execute(
        "SELECT lifecycle, mergeable, review_decision, unresolved_threads, merge_state FROM prs"
        " WHERE repo = ? AND number = ? AND seeded = 0",
        (repo, int(number)),
    ).fetchone()
    if pr is None or pr["lifecycle"] not in _CHECKED_LIFECYCLES:
        return None
    slugs = _unmergeable_slugs(pr)
    if ",".join(slugs) != slug_list:
        return None
    return _unmergeable_trigger(row["project"], row["party"], repo, int(number), head_sha, slugs)


_DEFERRED = {
    "ask_answered": _deferred_ask,
    "checks_failing": _deferred_checks,
    "pr_unmergeable": _deferred_unmergeable,
}


def deferred_trigger(conn, row):
    rebuild = _DEFERRED.get(row["rule"])
    if rebuild is None:
        return None
    return rebuild(conn, row)


RULES = {"ask_answered": _ask_answered, "checks_failing": _checks_failing, "pr_unmergeable": _pr_unmergeable, "pr_promote": _pr_promote}


def _next_task_triggers(ctx, project_config):
    project = project_config["name"]
    parties = ctx.conn.execute(
        "SELECT name, generation FROM parties WHERE project = ? AND state = 'awaiting-leader' AND keeper = 0 ORDER BY name",
        (project,),
    ).fetchall()
    triggers = []
    for party in parties:
        item = next_commands.next_task_item(ctx, {"party": party["name"], "project": project})
        if item is None:
            continue
        subject = "{}/{}".format(item["quest"], item["tid"])
        prompt = "{} Dispatched: next task {}; run guild next.".format(resume.RESUME_PROMPT, subject)
        triggers.append(Trigger(project, "next_task", "next_task:{}:g{}:{}".format(party["name"], party["generation"], subject), party["name"], subject, prompt))
    return triggers


def _merge_head_triggers(ctx, project_config):
    project = project_config["name"]
    triggers = []
    for scope, entry in merge_queue_commands.scope_heads(ctx.conn, ctx.now):
        owner = ctx.conn.execute("SELECT project FROM parties WHERE name = ?", (entry["party"],)).fetchone()
        if owner is None or owner["project"] != project:
            continue
        text = "{}: {} is first in the merge queue; run guild pr ready-check {}".format(
            entry["party"], entry["ref"], entry["ref"]
        )
        triggers.append(
            Trigger(project, "merge_head", "merge_head:{}:{}".format(scope, entry["ref"]), entry["party"], entry["ref"], text)
        )
    return triggers


def _limit_resume_triggers(ctx, project_config):
    project = project_config["name"]
    live = session_info.live_session_ids(ctx.sessions_dir)
    parties = ctx.conn.execute(
        "SELECT name, leader_session_id FROM parties WHERE project = ? AND state != 'closed' ORDER BY name",
        (project,),
    ).fetchall()
    triggers = []
    for party in parties:
        if party["leader_session_id"] not in live:
            continue
        transcript = revive.find_transcript(paths.claude_projects_dir(), party["leader_session_id"])
        reset = None if transcript is None else transcript_usage.rate_limit_reset(transcript)
        if reset is None or ctx.now.timestamp() < reset + _RESUME_GRACE_SECONDS:
            continue
        key = "limit_resume:{}:{}".format(party["name"], reset)
        triggers.append(Trigger(project, "limit_resume", key, party["name"], str(reset), _RESUME_TEXT))
    return triggers


def _sdd_commit_time(sdd_config, sdd_path):
    if sdd_path.startswith("git:"):
        ref, path = sdd_path[4:].split(":", 1)
        return sdd.last_commit_time(sdd_config["git_repo"], ref, path)
    return sdd.last_commit_time(str(Path(sdd_path).parent), None, sdd_path)


def _sdd_commit_time_or_none(sdd_config, sdd_path):
    try:
        return _sdd_commit_time(sdd_config, sdd_path)
    except sdd.GitSddError:
        return None


def _sdd_progress_triggers(ctx, project_config):
    sdd_config = project_config.get("sdd")
    if sdd_config is None:
        return []
    now = ctx.now.timestamp()
    rows = ctx.conn.execute(
        "SELECT quests.party AS party, quests.slug AS quest, quests.epic AS epic, quest_tasks.tid AS tid,"
        " epics.sdd_path AS sdd_path,"
        " (SELECT MAX(events.ts) FROM events WHERE events.kind = 'task.started'"
        "  AND json_extract(events.payload, '$.quest') = quests.slug"
        "  AND json_extract(events.payload, '$.tid') = quest_tasks.tid) AS started"
        " FROM quest_tasks JOIN quests ON quests.slug = quest_tasks.quest"
        " JOIN epics ON epics.project = quests.project AND epics.epic = quests.epic"
        " WHERE quests.project = ? AND quest_tasks.state = 'active' ORDER BY quests.slug, quest_tasks.tid",
        (project_config["name"],),
    ).fetchall()
    commit_times = {}
    triggers = []
    for row in rows:
        if now - timeutil.from_iso(row["started"]).timestamp() <= _SDD_PROGRESS_SECONDS:
            continue
        if row["sdd_path"] not in commit_times:
            commit_times[row["sdd_path"]] = _sdd_commit_time_or_none(sdd_config, row["sdd_path"])
        committed = commit_times[row["sdd_path"]]
        if committed is None or now - committed <= _SDD_PROGRESS_SECONDS:
            continue
        subject = "{}/{}".format(row["quest"], row["tid"])
        key = "sdd_progress:{}:{}:{}".format(row["party"], subject, ctx.now.strftime("%Y-%m-%d"))
        text = "{}: record progress of {} in {} tasks.md (no SDD update in 24h)".format(
            row["party"], row["tid"], row["epic"]
        )
        triggers.append(Trigger(project_config["name"], "sdd_progress", key, row["party"], subject, text))
    return triggers


STATE_RULES = {
    "next_task": _next_task_triggers,
    "merge_head": _merge_head_triggers,
    "limit_resume": _limit_resume_triggers,
    "sdd_progress": _sdd_progress_triggers,
}
NOTIFY_ONLY_RULES = ("merge_head", "sdd_progress")
NUDGE_RULES = ("limit_resume",)
