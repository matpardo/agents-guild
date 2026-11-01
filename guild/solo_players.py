from guild import timeutil

COOLDOWN = "1h"
LAUNCH_COMMAND = "guild solo launch {} {}"

_RED_MAIN_PROMPT = (
    "Main of {repo} is red. Read its failing checks (`gh run list --branch <base> --repo {repo}`, `gh pr checks`),"
    " reproduce the failure locally and fix it with TDD in a worktree. Open a PR and track it with"
    " `guild pr track ... --fixes-main` (add `--fixes-flaky` when the failure is flaky). Mark the PR ready once CI"
    ' is green. Never merge. End with `guild adventurer done --pending "<text>"`.'
)
_DEPENDABOT_PROMPT = (
    "For each open Dependabot PR on {repo} apply these gates: identity (the author is dependabot[bot]), scope (only"
    " dependency pins change; no new steps or permissions), supply chain (an action SHA equals the commit of its"
    " tag; package hashes match the registry) and read the release notes on major bumps. Then push direct fixes on"
    " the PR branch (version strings, hashes, formatter output, a tool `required-version` bump) so the PR becomes"
    " mergeable. Also fix a failing Dependabot update run of {repo} through a normal PR. Never merge. Report what"
    ' still needs a human. End with `guild adventurer done --pending "<text>"`.'
)
JOBS = {
    "red-main": {"class": "cleric", "prompt": _RED_MAIN_PROMPT},
    "dependabot": {"class": "artificer", "prompt": _DEPENDABOT_PROMPT},
}


def health_job_name(repo, job):
    return "{}-{}".format(job, repo.replace("/", "-"))


def _players(project_data):
    return project_data.get("solo_players", [])


def jobs(project_data):
    return [
        {
            "name": health_job_name(player["repo"], player["job"]),
            "command": JOBS[player["job"]]["prompt"].format(repo=player["repo"]),
            "every": COOLDOWN,
        }
        for player in _players(project_data)
    ]


def _red_main_trigger(conn, repo):
    rows = conn.execute(
        "SELECT reason FROM main_status WHERE repo = ? AND red = 1 AND external IS NULL ORDER BY source", (repo,)
    ).fetchall()
    if not rows:
        return None
    return "main red: {}".format(rows[0]["reason"] or "marked red")


def _dependabot_trigger(conn, repo):
    row = conn.execute("SELECT unmergeable, run_failed FROM dependabot_status WHERE repo = ?", (repo,)).fetchone()
    if row is None:
        return None
    reasons = []
    if row["unmergeable"] > 0:
        reasons.append("{} unmergeable dependabot PRs".format(row["unmergeable"]))
    if row["run_failed"]:
        reasons.append("dependabot update run failing")
    return ", ".join(reasons) or None


_TRIGGERS = {"red-main": _red_main_trigger, "dependabot": _dependabot_trigger}


def _last_report(conn, project, health_job):
    row = conn.execute(
        "SELECT done_at, pending FROM adventurers WHERE project = ? AND health_job = ?"
        " AND state IN ('done', 'dismissed') ORDER BY done_at DESC LIMIT 1",
        (project, health_job),
    ).fetchone()
    if row is None:
        return None, None
    return row["done_at"], row["pending"]


def _state(conn, now, project, health_job, trigger, last_done):
    running = conn.execute(
        "SELECT 1 FROM adventurers WHERE project = ? AND health_job = ? AND state = 'active'",
        (project, health_job),
    ).fetchone()
    if running is not None:
        return "running"
    if trigger is None:
        return "idle"
    if last_done is not None and now - timeutil.from_iso(last_done) < timeutil.parse_duration(COOLDOWN):
        return "cooling"
    return "due"


def models(conn, now, projects_by_name):
    result = []
    for project in sorted(projects_by_name):
        for player in _players(projects_by_name[project]):
            health_job = health_job_name(player["repo"], player["job"])
            trigger = _TRIGGERS[player["job"]](conn, player["repo"])
            last_done, last_pending = _last_report(conn, project, health_job)
            result.append(
                {
                    "project": project,
                    "repo": player["repo"],
                    "job": player["job"],
                    "class": JOBS[player["job"]]["class"],
                    "name": player.get("name", player["job"]),
                    "health_job": health_job,
                    "trigger": trigger,
                    "state": _state(conn, now, project, health_job, trigger, last_done),
                    "last_done": last_done,
                    "last_pending": last_pending,
                    "launch": LAUNCH_COMMAND.format(player["repo"], player["job"]),
                }
            )
    return result
