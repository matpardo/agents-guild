import fnmatch
import json
from pathlib import Path

from guild import names, timeutil
from guild.errors import GuildError

_REQUIRED_KEYS = ("name", "paths", "github")
TRACKER_KINDS = ("jira-acli",)
_TRACKER_BROWSE_URL_PREFIX = "https://"
_LIFECYCLE_EVENTS = ("on_pr_merged", "on_pr_closed")
_LIFECYCLE_ENTRY_KEYS = {"command", "timeout_minutes"}
_LIFECYCLE_MAX_TIMEOUT_MINUTES = 1440
_HANDOFF_RETENTION_MAX_DAYS = 3650


def _validate_tracker_config(tracker_config):
    if not isinstance(tracker_config, dict):
        raise GuildError("project config 'tracker' must be an object", 1)
    if tracker_config.get("kind") not in TRACKER_KINDS:
        raise GuildError(
            "project config 'tracker.kind' is required and must be one of {}".format(
                ", ".join(TRACKER_KINDS)
            ),
            1,
        )
    browse_url = tracker_config.get("browse_url")
    if browse_url is None:
        return
    if not isinstance(browse_url, str) or not browse_url.startswith(_TRACKER_BROWSE_URL_PREFIX):
        raise GuildError(
            "project config 'tracker.browse_url' must start with '{}'".format(
                _TRACKER_BROWSE_URL_PREFIX
            ),
            1,
        )


def _validate_notify_config(notify_config):
    if not isinstance(notify_config, dict):
        raise GuildError("project config 'notify' must be an object", 1)
    if set(notify_config) != {"command"}:
        raise GuildError("project config 'notify' must have exactly the key 'command'", 1)
    command = notify_config["command"]
    if not isinstance(command, list) or not command:
        raise GuildError("project config 'notify.command' must be a non-empty list of strings", 1)
    if not all(isinstance(item, str) and item for item in command):
        raise GuildError("project config 'notify.command' must be a non-empty list of strings", 1)


def _validate_shared_areas_config(data):
    shared_areas = data.get("shared_areas")
    if shared_areas is None:
        return
    if not isinstance(shared_areas, list) or not all(isinstance(item, str) for item in shared_areas):
        raise GuildError("project config 'shared_areas' must be a list of strings", 1)
    ttl = data.get("shared_area_claim_ttl")
    if ttl is None:
        raise GuildError(
            "project config 'shared_area_claim_ttl' is required when 'shared_areas' is set", 1
        )
    timeutil.parse_duration(ttl)


def _validate_migration_paths_config(data):
    migration_paths = data.get("migration_paths")
    if migration_paths is None:
        return
    if not isinstance(migration_paths, list) or not all(isinstance(item, str) for item in migration_paths):
        raise GuildError("project config 'migration_paths' must be a list of strings", 1)


def _validate_fast_forward_base_config(data):
    fast_forward_base = data.get("fast_forward_base")
    if fast_forward_base is None:
        return
    if not isinstance(fast_forward_base, bool):
        raise GuildError("project config 'fast_forward_base' must be a boolean", 1)


def _validate_max_open_prs_config(data, key):
    cap = data.get(key)
    if cap is None:
        return
    if isinstance(cap, bool) or not isinstance(cap, int) or cap <= 0:
        raise GuildError("project config '{}' must be a positive integer".format(key), 1)


def _validate_next_config(data):
    next_config = data.get("next")
    if next_config is None:
        return
    if not isinstance(next_config, dict):
        raise GuildError("project config 'next' must be an object", 1)
    if "stale_hours" not in next_config:
        return
    stale_hours = next_config["stale_hours"]
    if isinstance(stale_hours, bool) or not isinstance(stale_hours, int) or stale_hours <= 0:
        raise GuildError("project config 'next.stale_hours' must be a positive integer", 1)


def _validate_handoff_retention_config(data):
    days = data.get("handoff_retention_days")
    if days is None:
        return
    if isinstance(days, bool) or not isinstance(days, int) or days <= 0:
        raise GuildError("project config 'handoff_retention_days' must be a positive integer", 1)
    if days > _HANDOFF_RETENTION_MAX_DAYS:
        raise GuildError(
            "project config 'handoff_retention_days' must be at most {}".format(_HANDOFF_RETENTION_MAX_DAYS), 1
        )


def _validate_lifecycle_command(event, command):
    label = "project config 'lifecycle.{}.command' must be a non-empty list of strings".format(event)
    if not isinstance(command, list) or not command:
        raise GuildError(label, 1)
    if not all(isinstance(item, str) and item for item in command):
        raise GuildError(label, 1)


def _validate_lifecycle_timeout(event, timeout):
    if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout <= 0:
        raise GuildError(
            "project config 'lifecycle.{}.timeout_minutes' must be a positive integer".format(event), 1
        )
    if timeout > _LIFECYCLE_MAX_TIMEOUT_MINUTES:
        raise GuildError(
            "project config 'lifecycle.{}.timeout_minutes' must be at most {}".format(
                event, _LIFECYCLE_MAX_TIMEOUT_MINUTES
            ),
            1,
        )


def _validate_lifecycle_entry(event, entry):
    if not isinstance(entry, dict):
        raise GuildError(
            "project config 'lifecycle.{}' must be an object with 'command' and 'timeout_minutes'".format(
                event
            ),
            1,
        )
    if set(entry) != _LIFECYCLE_ENTRY_KEYS:
        raise GuildError(
            "project config 'lifecycle.{}' must have exactly the keys 'command' and 'timeout_minutes'".format(
                event
            ),
            1,
        )
    _validate_lifecycle_command(event, entry["command"])
    _validate_lifecycle_timeout(event, entry["timeout_minutes"])


def _validate_lifecycle_config(data):
    lifecycle = data.get("lifecycle")
    if lifecycle is None:
        return
    if not isinstance(lifecycle, dict):
        raise GuildError("project config 'lifecycle' must be an object", 1)
    for event in lifecycle:
        if event not in _LIFECYCLE_EVENTS:
            raise GuildError(
                "project config 'lifecycle' has unknown event '{}': allowed are {}".format(
                    event, ", ".join(_LIFECYCLE_EVENTS)
                ),
                1,
            )
    for event, entry in lifecycle.items():
        _validate_lifecycle_entry(event, entry)


def validate_project_config(data):
    for key in _REQUIRED_KEYS:
        if key not in data:
            raise GuildError("project config missing required key '{}'".format(key), 1)
    if not isinstance(data["name"], str) or not data["name"]:
        raise GuildError("project config 'name' must be a non-empty string", 1)
    names.validate_name(data["name"], "project name")
    if not isinstance(data["paths"], list) or not data["paths"]:
        raise GuildError("project config 'paths' must be a non-empty list", 1)
    if not isinstance(data["github"], dict) or not isinstance(data["github"].get("repos"), list):
        raise GuildError("project config 'github.repos' must be a list", 1)
    tracker_config = data.get("tracker")
    if tracker_config is not None:
        _validate_tracker_config(tracker_config)
    notify_config = data.get("notify")
    if notify_config is not None:
        _validate_notify_config(notify_config)
    _validate_shared_areas_config(data)
    _validate_migration_paths_config(data)
    _validate_fast_forward_base_config(data)
    _validate_lifecycle_config(data)
    _validate_next_config(data)
    _validate_handoff_retention_config(data)
    _validate_max_open_prs_config(data, "max_open_prs")
    _validate_max_open_prs_config(data, "max_open_prs_per_party")
    _validate_max_open_prs_config(data, "max_open_prs_per_file")
    _validate_max_open_prs_config(data, "finding_guard_threshold")


def load_project_file(config_file):
    try:
        raw = config_file.read_text()
    except OSError as error:
        raise GuildError("cannot read config file '{}': {}".format(config_file, error), 1)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as error:
        raise GuildError("invalid JSON in '{}': {}".format(config_file, error), 1)
    validate_project_config(data)
    return data


def load_all_projects(projects_dir):
    if not projects_dir.is_dir():
        return []
    projects = []
    for entry in sorted(projects_dir.glob("*.json")):
        projects.append(load_project_file(entry))
    return projects


def _known_projects_label(projects_dir):
    project_names = sorted(project["name"] for project in load_all_projects(projects_dir))
    if not project_names:
        return "none"
    return ", ".join(project_names)


def load_project(projects_dir, name):
    names.validate_name(name, "project name")
    config_file = projects_dir / "{}.json".format(name)
    if not config_file.is_file():
        raise GuildError(
            "unknown project '{}': known projects are {}".format(
                name, _known_projects_label(projects_dir)
            ),
            1,
        )
    return load_project_file(config_file)


def _ancestors(cwd):
    current = cwd
    seen = [current]
    while current.parent != current:
        current = current.parent
        seen.append(current)
    return seen


def resolve_project(cwd, projects):
    for project in projects:
        for pattern in project["paths"]:
            expanded = str(Path(pattern).expanduser())
            for ancestor in _ancestors(cwd):
                if fnmatch.fnmatch(str(ancestor), expanded):
                    return project["name"]
    return None


def require_project(cwd, projects_dir):
    projects = load_all_projects(projects_dir)
    name = resolve_project(cwd, projects)
    if name is None:
        raise GuildError(
            "no project config matches '{}': known projects are {} (run guild init-project)".format(
                cwd, _known_projects_label(projects_dir)
            ),
            1,
        )
    return name
