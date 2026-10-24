import re

from guild.errors import GuildError

_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def validate_name(value, field_name):
    if _NAME_RE.fullmatch(value) is None or ".." in value:
        raise GuildError(
            "invalid {} '{}': must match {} and must not contain '..'".format(
                field_name, value, _NAME_RE.pattern
            ),
            1,
        )
    return value


def ensure_within(path, base_dir):
    resolved_path = path.resolve()
    resolved_base = base_dir.resolve()
    if not resolved_path.is_relative_to(resolved_base):
        raise GuildError(
            "resolved path '{}' escapes '{}'".format(resolved_path, resolved_base), 1
        )
    return resolved_path
