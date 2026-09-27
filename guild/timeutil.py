import re
from datetime import datetime, timedelta, timezone

from guild.errors import GuildError

_DURATION_RE = re.compile(r"^(\d+)([mhd])$")
_UNIT_SECONDS = {"m": 60, "h": 3600, "d": 86400}


def utcnow():
    return datetime.now(timezone.utc)


def to_iso(moment):
    return moment.isoformat()


def from_iso(text):
    return datetime.fromisoformat(text)


def parse_duration(text):
    match = _DURATION_RE.match(text)
    if not match:
        raise GuildError(
            "invalid duration '{}': use formats like 30m, 8h, 3d".format(text), 1
        )
    amount, unit = match.groups()
    return timedelta(seconds=int(amount) * _UNIT_SECONDS[unit])


def expires_at_iso(now, duration_text):
    return to_iso(now + parse_duration(duration_text))


def is_expired(now, expires_at_text):
    return now > from_iso(expires_at_text)
