import math
import re
from datetime import datetime, timedelta, timezone

from guild.errors import GuildError

_DURATION_RE = re.compile(r"^(\d+)([mhd])$")
_UNIT_SECONDS = {"m": 60, "h": 3600, "d": 86400}

MEMBERSHIP_WARNING_WINDOW = timedelta(hours=12)


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
    if expires_at_text is None:
        return False
    return now > from_iso(expires_at_text)


def issued_label(issued_at_text):
    return from_iso(issued_at_text).astimezone().strftime("%Y-%m-%d %H:%M")


def clock_label(expires_at_text):
    return from_iso(expires_at_text).strftime("%H:%M")


def time_left_label(now, expires_at_text):
    remaining = from_iso(expires_at_text) - now
    hours = int(remaining.total_seconds() // 3600)
    if hours >= 1:
        return "{}h left".format(hours)
    return "{}m left".format(int(remaining.total_seconds() // 60))


def membership_left_label(now, expires_at_text):
    if expires_at_text is None:
        return "until leave"
    return time_left_label(now, expires_at_text)


def hours_until(now, expires_at_text):
    remaining = from_iso(expires_at_text) - now
    return max(1, math.ceil(remaining.total_seconds() / 3600))


def age_label(now, since_iso):
    seconds = max(0, int((now - from_iso(since_iso)).total_seconds()))
    if seconds < 60:
        return "{}s".format(seconds)
    if seconds < 3600:
        return "{}m".format(seconds // 60)
    if seconds < 86400:
        return "{}h".format(seconds // 3600)
    return "{}d".format(seconds // 86400)
