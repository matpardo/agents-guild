from guild import names, timeutil
from guild.errors import GuildError

MAX_PROJECTS = 50
_MAX_NAME_LENGTH = 64
_MAX_ISO_LENGTH = 64
_COUNT_KEYS = ("parties", "open_quests", "open_prs", "ready_prs", "open_asks")
_PROJECT_KEYS = frozenset(("name",) + _COUNT_KEYS + ("main_red",))
_STATUS_KEYS = frozenset(("guild", "generated_at", "projects"))
_INVALID = "invalid status"


def _reject():
    raise GuildError(_INVALID, 1)


def _check_name(value):
    if not isinstance(value, str) or not value or len(value) > _MAX_NAME_LENGTH:
        _reject()
    try:
        names.validate_name(value, "name")
    except GuildError:
        _reject()


def _check_count(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _reject()


def _check_iso(value):
    if not isinstance(value, str) or len(value) > _MAX_ISO_LENGTH:
        _reject()
    try:
        timeutil.from_iso(value)
    except ValueError:
        _reject()


def _check_project(project):
    if not isinstance(project, dict) or set(project) != _PROJECT_KEYS:
        _reject()
    _check_name(project["name"])
    for key in _COUNT_KEYS:
        _check_count(project[key])
    if not isinstance(project["main_red"], bool):
        _reject()


def validate(payload, expect_received_at):
    if not isinstance(payload, dict):
        _reject()
    expected_keys = _STATUS_KEYS | {"received_at"} if expect_received_at else _STATUS_KEYS
    if set(payload) != expected_keys:
        _reject()
    _check_name(payload["guild"])
    _check_iso(payload["generated_at"])
    if expect_received_at:
        _check_iso(payload["received_at"])
    projects = payload["projects"]
    if not isinstance(projects, list) or len(projects) > MAX_PROJECTS:
        _reject()
    for project in projects:
        _check_project(project)
    return payload
