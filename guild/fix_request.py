from datetime import timedelta

from guild import config, timeutil

_SEPARATOR = "·"


def _stale_hours(projects_dir, repo):
    for project in config.load_all_projects(projects_dir):
        if repo in project["github"]["repos"]:
            return project.get("fix_request_stale_hours")
    return None


def status(projects_dir, now, repo, party, requested_at):
    if requested_at is None:
        return None
    age = now - timeutil.from_iso(requested_at)
    stale_hours = _stale_hours(projects_dir, repo)
    return {
        "party": party,
        "at": requested_at,
        "age_hours": int(age.total_seconds() // 3600),
        "stale": stale_hours is not None and age > timedelta(hours=stale_hours),
    }


def label(request):
    if request["stale"]:
        return "fixing {} stale".format(_SEPARATOR)
    return "fixing {} {} {} {}h".format(_SEPARATOR, request["party"], _SEPARATOR, request["age_hours"])
