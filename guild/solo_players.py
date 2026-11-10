from pathlib import Path

from guild import localbase, sanitize, timeutil

COOLDOWN = "1h"
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


_GENERIC_RULES = (
    "Never merge. Track every PR you open with `guild pr track ...` without `--task`{fixes_main}."
    ' Tell the dev only important things with `guild solo say "<text>"`, no routine progress.'
    " Before finishing, post one short `guild solo say` with the PRs you touched and what needs a human;"
    " skip the long final report, the chat is the record."
    ' End with `guild adventurer done --pending "<text>"`; the window closes after it.'
)
_MAIN_RED = "main-red"
_DEPENDABOT = "dependabot"
_EVERY = "every"
_RETRY_AFTER = {_MAIN_RED: "4h", _DEPENDABOT: "24h"}


def _job(job_class, trigger, goal, steps, rules):
    return {"class": job_class, "trigger": trigger, "goal": goal, "rules": rules, "prompt": goal + steps + rules}


BUILTIN = {
    "red-main": _job("cleric", _MAIN_RED, _RED_MAIN_GOAL, _RED_MAIN_STEPS, _RED_MAIN_RULES),
    "dependabot": _job("artificer", _DEPENDABOT, _DEPENDABOT_GOAL, _DEPENDABOT_STEPS, _DEPENDABOT_RULES),
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


def player_class(player):
    if "class" in player:
        return player["class"]
    return BUILTIN[player["job"]]["class"]


def player_trigger(player):
    if "trigger" in player:
        return player["trigger"]
    return BUILTIN[player["job"]]["trigger"]


def trigger_kind(player):
    return player_trigger(player).split(" ")[0]


def player_retry_after(player):
    kind = trigger_kind(player)
    if kind == _EVERY:
        return None
    return player.get("retry_after", _RETRY_AFTER[kind])


def _prompt(player):
    if "command" not in player:
        return BUILTIN[player["job"]]["prompt"].format(repo=player["repo"])
    fixes_main = " and add `--fixes-main`" if trigger_kind(player) == _MAIN_RED else ""
    return player["command"] + "\n\n" + _GENERIC_RULES.format(fixes_main=fixes_main)


def jobs(project_data):
    return [
        {
            "name": health_job_name(player["repo"], player["job"]),
            "command": _prompt(player),
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
    job = BUILTIN[job_name]
    return "/{} {}\n\n".format(job_name, repo) + (job["goal"] + _SKILL_STEPS + job["rules"]).format(repo=repo)


def launch_job(project_data, player):
    repo = player["repo"]
    job_name = player["job"]
    clone = _clone_path(project_data, repo)
    skill = (
        "command" not in player
        and clone is not None
        and Path(clone, ".claude", "skills", job_name, "SKILL.md").is_file()
    )
    command = _repo_skill_prompt(job_name, repo) if skill else _prompt(player)
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


def _every_next_at(conn, project, player):
    interval = timeutil.parse_duration(player_trigger(player)[len(_EVERY) + 1 :])
    health_job = health_job_name(player["repo"], player["job"])
    stamps = [
        stamp for stamp in (_last_report(conn, project, health_job)[0], _last_launch(conn, health_job)[0]) if stamp
    ]
    if not stamps:
        return None
    return max(timeutil.from_iso(stamp) for stamp in stamps) + interval


def _every_trigger(conn, now, project, player):
    next_at = _every_next_at(conn, project, player)
    if next_at is not None and next_at > now:
        return None
    return player_trigger(player)


def current_trigger(conn, now, project, player):
    kind = trigger_kind(player)
    if kind == _MAIN_RED:
        return _red_main_trigger(conn, player["repo"])
    if kind == _DEPENDABOT:
        return _dependabot_trigger(conn, player["repo"])
    return _every_trigger(conn, now, project, player)


def _fix_prs(conn, player):
    if trigger_kind(player) != _MAIN_RED:
        return []
    rows = conn.execute(
        "SELECT number FROM prs WHERE repo = ? AND fixes_main = 1 AND lifecycle NOT IN ('merged', 'closed')"
        " ORDER BY number",
        (player["repo"],),
    ).fetchall()
    return ["{}#{}".format(player["repo"], row["number"]) for row in rows]


def active_adventurer(conn, project, health_job):
    return conn.execute(
        "SELECT id, session_id FROM adventurers WHERE project = ? AND health_job = ? AND state = 'active'",
        (project, health_job),
    ).fetchone()


def is_paused(conn, health_job):
    return conn.execute("SELECT 1 FROM solo_pauses WHERE health_job = ?", (health_job,)).fetchone() is not None


def _retry_at(now, retry_after, trigger, last_done, last_launch, last_launch_trigger):
    repeats = retry_after is not None and trigger == last_launch_trigger
    cooldown = timeutil.parse_duration(retry_after if repeats else COOLDOWN)
    ends = [timeutil.from_iso(stamp) + cooldown for stamp in (last_done, last_launch) if stamp is not None]
    pending = [end for end in ends if end > now]
    if not pending:
        return None
    return max(pending)


def _state(now, active, live_ids, paused, retry_after, trigger, fix_prs, last_done, last_launch, last_launch_trigger):
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
    if _retry_at(now, retry_after, trigger, last_done, last_launch, last_launch_trigger) is not None:
        return "cooling"
    return "due"


def _repeat_retry(now, state, retry_after, trigger, last_done, last_launch, last_launch_trigger):
    if state != "cooling" or trigger != last_launch_trigger:
        return None
    return timeutil.to_iso(_retry_at(now, retry_after, trigger, last_done, last_launch, last_launch_trigger))


def _next_run_at(state, cooling_until, every_next_at):
    if state == "cooling":
        return timeutil.to_iso(cooling_until)
    if state == "idle" and every_next_at is not None:
        return timeutil.to_iso(every_next_at)
    return None


def next_run_label(row):
    if row["next_run_at"] is not None:
        return row["next_run_at"]
    return "next tick" if row["state"] == "due" else "none"


def state_detail(row):
    if row["stalled_adventurer"] is not None:
        return ": session gone, run guild adventurer dismiss {}".format(row["stalled_adventurer"])
    if row["retry_at"] is not None:
        return ": same trigger"
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


def _run_prs(conn, adventurer_id):
    rows = conn.execute(
        "SELECT repo, number, lifecycle FROM prs WHERE adventurer = ? ORDER BY repo, number", (adventurer_id,)
    ).fetchall()
    return [{"ref": "{}#{}".format(row["repo"], row["number"]), "lifecycle": row["lifecycle"]} for row in rows]


def runs(conn, project, health_job, live_ids, limit):
    rows = conn.execute(
        "SELECT id, session_id, state, started_at, done_at, pending FROM adventurers"
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
            "prs": _run_prs(conn, row["id"]),
        }
        for row in rows
    ]


def models(conn, now, projects_by_name, live_ids):
    result = []
    ready = ready_to_merge(conn, projects_by_name)
    for project in sorted(projects_by_name):
        for player in _players(projects_by_name[project]):
            health_job = health_job_name(player["repo"], player["job"])
            kind = trigger_kind(player)
            retry_after = player_retry_after(player)
            trigger = current_trigger(conn, now, project, player)
            active = active_adventurer(conn, project, health_job)
            fix_prs = _fix_prs(conn, player)
            last_done, last_pending = _last_report(conn, project, health_job)
            last_launch, last_launch_trigger = _last_launch(conn, health_job)
            state = _state(
                now,
                active,
                live_ids,
                is_paused(conn, health_job),
                retry_after,
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
                    "class": player_class(player),
                    "name": player_name(player),
                    "health_job": health_job,
                    "trigger": trigger,
                    "schedule": player_trigger(player),
                    "state": state,
                    "retry_after": retry_after,
                    "retry_at": _repeat_retry(
                        now, state, retry_after, trigger, last_done, last_launch, last_launch_trigger
                    ),
                    "next_run_at": _next_run_at(
                        state,
                        _retry_at(now, retry_after, trigger, last_done, last_launch, last_launch_trigger),
                        _every_next_at(conn, project, player) if kind == _EVERY else None,
                    ),
                    "stalled_adventurer": None if active is None or active["session_id"] in live_ids else active["id"],
                    "waits_on": fix_prs,
                    "last_done": last_done,
                    "last_pending": last_pending,
                    "runs": runs(conn, project, health_job, live_ids, RUNS_SHOWN),
                    "to_merge": [entry for entry in ready if kind == _DEPENDABOT and entry["repo"] == player["repo"]],
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
            if trigger_kind(player) == _DEPENDABOT:
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
