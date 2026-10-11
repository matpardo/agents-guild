from guild import merge_queue, resume


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
        " prs.merge_state AS merge_state FROM prs"
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
    slugs = _unmergeable_slugs(owner)
    if not slugs:
        return None
    return _unmergeable_trigger(owner["project"], owner["party"], repo, number, payload["head_sha"], slugs)


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


RULES = {"ask_answered": _ask_answered, "checks_failing": _checks_failing, "pr_unmergeable": _pr_unmergeable}
