from guild import resume


_CHECKED_LIFECYCLES = ("draft", "converging", "ready")


class Trigger:
    def __init__(self, project, rule, key, party, subject, prompt):
        self.project = project
        self.rule = rule
        self.key = key
        self.party = party
        self.subject = subject
        self.prompt = prompt


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
    prompt = "{} Dispatched: ask #{} was answered; read guild asks {}.".format(
        resume.RESUME_PROMPT, ask_id, ask_id
    )
    return Trigger(
        ask["project"], "ask_answered", "ask_answered:{}".format(ask_id), ask["party"], "ask #{}".format(ask_id), prompt
    )


def _checks_failing(conn, projects, event):
    if event["kind"] != "pr.synced":
        return None
    payload = event["payload"]
    if payload["lifecycle"] not in _CHECKED_LIFECYCLES:
        return None
    if payload["checks_failing"] <= 0 or payload.get("checks_pending") != 0 or not payload.get("head_sha"):
        return None
    repo, number = payload["repo"], payload["number"]
    owner = conn.execute(
        "SELECT prs.party AS party, parties.project AS project FROM prs"
        " JOIN parties ON parties.name = prs.party WHERE prs.repo = ? AND prs.number = ? AND prs.seeded = 0",
        (repo, number),
    ).fetchone()
    if owner is None or owner["project"] not in projects:
        return None
    if repo not in projects[owner["project"]]["github"]["repos"]:
        return None
    subject = "{}#{}".format(repo, number)
    prompt = "{} Dispatched: checks fail on {}; run gh pr checks {} --repo {}.".format(
        resume.RESUME_PROMPT, subject, number, repo
    )
    key = "checks_failing:{}:{}".format(subject, payload["head_sha"])
    return Trigger(owner["project"], "checks_failing", key, owner["party"], subject, prompt)


RULES = {"ask_answered": _ask_answered, "checks_failing": _checks_failing}
