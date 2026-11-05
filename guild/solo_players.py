from pathlib import Path

from guild import localbase, sanitize, timeutil

COOLDOWN = "1h"
REPEAT_COOLDOWN = "24h"
RUNS_SHOWN = 5
LAUNCH_COMMAND = "guild solo launch {} {}"
RESUME_COMMAND = "guild solo resume {} {}"

_RED_MAIN_GOAL = "Main of {repo} is red: get it green."
_RED_MAIN_STEPS = (
    " Read its failing checks (`gh run list --branch <base> --repo {repo}`, `gh pr checks`), reproduce the failure"
    " locally and fix it with TDD in a worktree. Open a PR and mark it ready once CI is green."
)
_RED_MAIN_RULES = (
    " Track the fix PR with `guild pr track ... --fixes-main` (add `--fixes-flaky` when the failure is flaky)."
    ' Never merge. Tell the dev only important things with `guild solo say "<text>"`, no routine'
    ' progress: `guild solo say "started fixing: <cause>"` when you know the cause, then `guild solo say "fix PR'
    ' {repo}#<n> ready, waits on merge"` (or `guild solo say "main green, nothing to do"`). Before finishing, post one short `guild solo say` with the PRs you touched and what needs a human; skip the long final report, the chat is the record. End with `guild adventurer done --pending "<text>"`; the window closes after it.'
)
_DEPENDABOT_GOAL = "Get the open Dependabot PRs of {repo} mergeable and its Dependabot update runs passing."
_DEPENDABOT_STEPS = (
    " For each open Dependabot PR on {repo} apply these gates: stale (compare each target version with the pin in the"
    " manifest and lock on the base branch; a dependency is stale when the base already pins that version or a"
    " newer one. A stale single-dependency PR: comment `@dependabot close` and tell the dev with `guild solo say"
    ' "{repo}#<n> closed: already at <version>"`. A stale dependency in a multi-dependency PR: never update a stale'
    " dependency, push a fix on the PR branch that restores its base pin and keeps the live bumps; when unsure"
    " whether it is stale, do not close, say it needs a human. The comment has no guild words), identity (the author is dependabot[bot]), scope (only"
    " dependency pins change; no new steps or permissions), supply chain (an action SHA equals the commit of its"
    " tag; package hashes match the registry) and read the release notes on major bumps. Then push direct fixes on"
    " the PR branch (version strings, hashes, formatter output, a tool `required-version` bump) so the PR becomes"
    " mergeable. Also fix a failing Dependabot update run of {repo} through a normal PR."
)
_DEPENDABOT_RULES = (
    " Never merge. Report what still needs a human. Tell the dev only important things with `guild solo say"
    ' "<text>"`, no routine progress: `guild solo say "{repo}#<n> needs a human: <why>"`. Guild itself announces'
    " the PRs that turn green. Before finishing, post one short `guild solo say` with the PRs you touched and what"
    " needs a human; skip the long final report, the chat is the record."
    ' End with `guild adventurer done --pending "<text>"`; the window closes after it.'
)
_SKILL_STEPS = (
    " Follow the repo skill above for the steps. Where it disagrees with these rules, the rules win on merging,"
    " guild tracking and messages; the skill wins on the repo's own steps, such as how a PR becomes ready."
)


def _job(job_class, goal, steps, rules):
    return {"class": job_class, "goal": goal, "rules": rules, "prompt": goal + steps + rules}


JOBS = {
    "red-main": _job("cleric", _RED_MAIN_GOAL, _RED_MAIN_STEPS, _RED_MAIN_RULES),
    "dependabot": _job("artificer", _DEPENDABOT_GOAL, _DEPENDABOT_STEPS, _DEPENDABOT_RULES),
}


def health_job_name(repo, job):
    return "{}-{}".format(job, repo.replace("/", "-"))


def _players(project_data):
    return project_data.get("solo_players", [])


def player_of_health_job(project_data, health_job):
    for player in _players(project_data):
        if health_job_name(player["repo"], player["job"]) == health_job:
            return player
    return None


def player_name(player):
    return player.get("name", player["job"])


def jobs(project_data):
    return [
        {
            "name": health_job_name(player["repo"], player["job"]),
            "command": JOBS[player["job"]]["prompt"].format(repo=player["repo"]),
            "every": COOLDOWN,
        }
        for player in _players(project_data)
    ]


def _clone_path(project_data, repo):
    for clone in localbase.locate_clones(project_data):
        if clone["repo"] == repo:
            return clone["path"]
    return None


def _repo_skill_prompt(job_name, repo):
    job = JOBS[job_name]
    return "/{} {}\n\n".format(job_name, repo) + (job["goal"] + _SKILL_STEPS + job["rules"]).format(repo=repo)


def launch_job(project_data, repo, job_name):
    clone = _clone_path(project_data, repo)
    skill = clone is not None and Path(clone, ".claude", "skills", job_name, "SKILL.md").is_file()
    command = _repo_skill_prompt(job_name, repo) if skill else JOBS[job_name]["prompt"].format(repo=repo)
    return {"name": health_job_name(repo, job_name), "command": command, "every": COOLDOWN, "cwd": clone}


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


def _last_launch(conn, health_job):
    row = conn.execute("SELECT launched_at, trigger FROM solo_launches WHERE health_job = ?", (health_job,)).fetchone()
    if row is None:
        return None, None
    return row["launched_at"], row["trigger"]


def current_trigger(conn, repo, job):
    return _TRIGGERS[job](conn, repo)


def _fix_prs(conn, repo, job):
    if job != "red-main":
        return []
    rows = conn.execute(
        "SELECT number FROM prs WHERE repo = ? AND fixes_main = 1 AND lifecycle NOT IN ('merged', 'closed')"
        " ORDER BY number",
        (repo,),
    ).fetchall()
    return ["{}#{}".format(repo, row["number"]) for row in rows]


def active_adventurer(conn, project, health_job):
    return conn.execute(
        "SELECT id, session_id FROM adventurers WHERE project = ? AND health_job = ? AND state = 'active'",
        (project, health_job),
    ).fetchone()


def is_paused(conn, health_job):
    return conn.execute("SELECT 1 FROM solo_pauses WHERE health_job = ?", (health_job,)).fetchone() is not None


def _retry_at(now, trigger, last_done, last_launch, last_launch_trigger):
    cooldown = timeutil.parse_duration(REPEAT_COOLDOWN if trigger == last_launch_trigger else COOLDOWN)
    ends = [timeutil.from_iso(stamp) + cooldown for stamp in (last_done, last_launch) if stamp is not None]
    pending = [end for end in ends if end > now]
    if not pending:
        return None
    return max(pending)


def _state(now, active, live_ids, paused, trigger, fix_prs, last_done, last_launch, last_launch_trigger):
    if active is not None and active["session_id"] in live_ids:
        return "running"
    if active is not None:
        return "stalled"
    if paused:
        return "paused"
    if fix_prs:
        return "fixing"
    if trigger is None:
        return "idle"
    if _retry_at(now, trigger, last_done, last_launch, last_launch_trigger) is not None:
        return "cooling"
    return "due"


def _repeat_retry(now, state, trigger, last_done, last_launch, last_launch_trigger):
    if state != "cooling" or trigger != last_launch_trigger:
        return None
    return timeutil.to_iso(_retry_at(now, trigger, last_done, last_launch, last_launch_trigger))


def state_detail(row):
    if row["stalled_adventurer"] is not None:
        return ": session gone, run guild adventurer dismiss {}".format(row["stalled_adventurer"])
    if row["retry_at"] is not None:
        return ": same trigger, retry after {}".format(row["retry_at"])
    if row["waits_on"]:
        return ": waits on {}".format(", ".join(row["waits_on"]))
    return ""


def _run_state(row, live_ids):
    if row["state"] != "active":
        return row["state"]
    return "running" if row["session_id"] in live_ids else "stalled"


def _run_duration(row):
    if row["done_at"] is None:
        return None
    return int((timeutil.from_iso(row["done_at"]) - timeutil.from_iso(row["started_at"])).total_seconds())


def runs(conn, project, health_job, live_ids, limit):
    rows = conn.execute(
        "SELECT session_id, state, started_at, done_at, pending FROM adventurers"
        " WHERE project = ? AND health_job = ? ORDER BY id DESC LIMIT ?",
        (project, health_job, limit),
    ).fetchall()
    return [
        {
            "started_at": row["started_at"],
            "done_at": row["done_at"],
            "state": _run_state(row, live_ids),
            "duration": _run_duration(row),
            "pending": row["pending"],
        }
        for row in rows
    ]


def models(conn, now, projects_by_name, live_ids):
    result = []
    ready = ready_to_merge(conn, projects_by_name)
    for project in sorted(projects_by_name):
        for player in _players(projects_by_name[project]):
            health_job = health_job_name(player["repo"], player["job"])
            trigger = _TRIGGERS[player["job"]](conn, player["repo"])
            active = active_adventurer(conn, project, health_job)
            fix_prs = _fix_prs(conn, player["repo"], player["job"])
            last_done, last_pending = _last_report(conn, project, health_job)
            last_launch, last_launch_trigger = _last_launch(conn, health_job)
            state = _state(
                now,
                active,
                live_ids,
                is_paused(conn, health_job),
                trigger,
                fix_prs,
                last_done,
                last_launch,
                last_launch_trigger,
            )
            result.append(
                {
                    "project": project,
                    "repo": player["repo"],
                    "job": player["job"],
                    "class": JOBS[player["job"]]["class"],
                    "name": player_name(player),
                    "health_job": health_job,
                    "trigger": trigger,
                    "state": state,
                    "retry_at": _repeat_retry(now, state, trigger, last_done, last_launch, last_launch_trigger),
                    "stalled_adventurer": None if active is None or active["session_id"] in live_ids else active["id"],
                    "waits_on": fix_prs,
                    "last_done": last_done,
                    "last_pending": last_pending,
                    "runs": runs(conn, project, health_job, live_ids, RUNS_SHOWN),
                    "to_merge": [
                        entry for entry in ready if player["job"] == "dependabot" and entry["repo"] == player["repo"]
                    ],
                    "launch": (RESUME_COMMAND if state == "paused" else LAUNCH_COMMAND).format(
                        player["repo"], player["job"]
                    ),
                }
            )
    return result


def ready_to_merge(conn, projects_by_name):
    names = {}
    for project in sorted(projects_by_name):
        for player in _players(projects_by_name[project]):
            if player["job"] == "dependabot":
                names.setdefault(player["repo"], player_name(player))
    rows = conn.execute("SELECT repo, number, title FROM dependabot_ready ORDER BY repo, number").fetchall()
    return [
        {
            "ref": "{}#{}".format(row["repo"], row["number"]),
            "repo": row["repo"],
            "title": row["title"],
            "url": "https://github.com/{}/pull/{}".format(row["repo"], row["number"]),
            "name": names[row["repo"]],
        }
        for row in rows
        if row["repo"] in names
    ]


def to_merge_lines(row):
    return ["    to merge: {} {}".format(entry["ref"], entry["title"]) for entry in row["to_merge"]]


def needs_human(conn, now, projects_by_name, live_ids):
    return [
        {
            "name": model["name"],
            "class": model["class"],
            "repo": model["repo"],
            "pending": sanitize.collapse_to_single_line(sanitize.strip_control_sequences(model["last_pending"])),
        }
        for model in models(conn, now, projects_by_name, live_ids)
        if model["trigger"] is not None
        and model["last_pending"] is not None
        and model["last_pending"].strip().lower() not in ("", "none")
    ]
