import json
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

from guild import paths, timeutil
from guild.errors import GuildError
from guild.realm import client, clientconfig, hubconfig

_PUSH_STALE = timedelta(minutes=15)
_MEMBER_STALE = timedelta(hours=1)
_MAX_SKEW = timedelta(minutes=2)
_CERT_WARN = timedelta(days=30)
_OPENSSL_END_FORMAT = "notAfter=%b %d %H:%M:%S %Y GMT"


def _ok(text):
    return (True, "ok      " + text)


def _warn(text):
    return (True, "warn    " + text)


def _fail(text):
    return (False, "fail    " + text)


def config_lines():
    path = paths.realm_config_path()
    if not path.exists():
        return []
    lines = []
    if path.stat().st_mode & 0o077:
        lines.append((False, "invalid realm config {}: mode must be 0600".format(path)))
    try:
        found = clientconfig.problems(json.loads(path.read_text(encoding="utf-8")))
    except ValueError:
        found = ["not valid JSON"]
    if found:
        return lines + [(False, "invalid realm config {}: {}".format(path, "; ".join(found)))]
    return lines + [(True, "ok      realm config")]


def _identity_lines(config, status_code, payload):
    if status_code != 200:
        return [_fail("token not accepted: " + client.refusal(status_code, payload))]
    lines = [_ok("token accepted")]
    if payload.get("member") != config["guild"]:
        lines.append(_fail("token belongs to {}, this guild is {}".format(payload.get("member"), config["guild"])))
    else:
        lines.append(_ok("member matches this guild"))
    if payload.get("realm") != config["realm"]:
        lines.append(_fail("hub calls its realm {}, this guild joined {}".format(payload.get("realm"), config["realm"])))
    else:
        lines.append(_ok("realm matches {}".format(config["realm"])))
    return lines


def _skew_lines(date_header, now):
    if date_header is None:
        return [_warn("hub sent no Date header: clock skew not checked")]
    try:
        hub_now = parsedate_to_datetime(date_header)
    except (TypeError, ValueError):
        return [_warn("hub sent an unreadable Date header: clock skew not checked")]
    skew = abs(now - hub_now)
    if skew > _MAX_SKEW:
        return [_warn("clock differs from the hub by {}s: fix the system clock".format(int(skew.total_seconds())))]
    return [_ok("clock agrees with the hub")]


def _push_lines(config, now):
    try:
        status_code, payload, _ = client.exchange(config, "GET", "/status", None)
    except GuildError as error:
        return [_fail(error.message)]
    if status_code != 200:
        return [_fail("could not read status: " + client.refusal(status_code, payload))]
    entries = payload.get("guilds")
    own = [entry for entry in entries if isinstance(entry, dict) and entry.get("guild") == config["guild"]] if isinstance(entries, list) else []
    if not own:
        return [_warn("this guild never pushed")]
    received_at = own[0].get("received_at")
    try:
        age = now - timeutil.from_iso(received_at)
    except (TypeError, ValueError):
        return [_fail("hub sent an invalid status")]
    label = timeutil.age_label(now, received_at)
    if age > _PUSH_STALE:
        return [_warn("last push {} ago: is the push timer running?".format(label))]
    return [_ok("last push {} ago".format(label))]


def guild_lines(now):
    lines = config_lines()
    if not lines:
        return [_ok("no realm joined")]
    if not all(passed for passed, _ in lines):
        return lines
    config = clientconfig.load()
    try:
        status_code, payload, date_header = client.exchange(config, "GET", "/whoami", None)
    except GuildError as error:
        return lines + [_fail(error.message)]
    lines.append(_ok("hub reachable over TLS 1.3 with the pinned fingerprint"))
    lines.extend(_identity_lines(config, status_code, payload))
    lines.extend(_skew_lines(date_header, now))
    if status_code != 200:
        return lines
    return lines + _push_lines(config, now)


def _mode_line(path, mode, label):
    if not path.exists():
        return _fail("{} missing: {}".format(label, path))
    actual = path.stat().st_mode & 0o777
    if actual != mode:
        return _fail("{} {} mode is {:o}, must be {:o}".format(label, path, actual, mode))
    return _ok("{} mode {:o}".format(label, mode))


def _cert_end(cert_path):
    openssl = shutil.which("openssl")
    if openssl is None:
        return None
    result = subprocess.run(
        [openssl, "x509", "-enddate", "-noout", "-in", str(cert_path)], capture_output=True, text=True
    )
    if result.returncode != 0:
        raise GuildError("openssl could not read the hub certificate", 1)
    try:
        return datetime.strptime(result.stdout.strip(), _OPENSSL_END_FORMAT).replace(tzinfo=timezone.utc)
    except ValueError:
        raise GuildError("openssl printed an unreadable certificate end date", 1)


def _cert_lines(cert_path, now):
    try:
        end = _cert_end(cert_path)
    except GuildError as error:
        return [_fail(error.message)]
    if end is None:
        return [_warn("openssl not found on PATH: certificate expiry not checked")]
    if end <= now:
        return [_fail("hub certificate expired {}".format(end.date()))]
    if end - now < _CERT_WARN:
        return [_warn("hub certificate expires in {} days: re-create it and re-join every guild".format((end - now).days))]
    return [_ok("hub certificate valid until {}".format(end.date()))]


def _member_line(name, now):
    path = paths.realm_hub_store_dir() / "status" / (name + ".json")
    try:
        received_at = json.loads(path.read_text(encoding="utf-8"))["received_at"]
        age = now - timeutil.from_iso(received_at)
    except FileNotFoundError:
        return _warn("member {} never pushed".format(name))
    except (OSError, ValueError, KeyError, TypeError):
        return _warn("member {} has an unreadable status file".format(name))
    if age > _MEMBER_STALE:
        return _warn("member {} last pushed {} ago".format(name, timeutil.age_label(now, received_at)))
    return _ok("member {} pushed {} ago".format(name, timeutil.age_label(now, received_at)))


def hub_lines(now):
    if not hubconfig.exists():
        return []
    lines = [_mode_line(paths.realm_hub_config_path(), 0o600, "hub config")]
    try:
        config = hubconfig.load()
    except GuildError as error:
        return lines + [_fail(error.message)]
    store = paths.realm_hub_store_dir()
    lines.append(_mode_line(Path(config["key"]), 0o600, "hub key"))
    lines.append(_mode_line(paths.realm_hub_pki_dir(), 0o700, "hub pki dir"))
    lines.extend(_mode_line(path, 0o700, "hub store dir") for path in (store, store / "status", store / "inbox") if path.exists())
    lines.extend(_cert_lines(config["cert"], now))
    lines.extend(_member_line(name, now) for name in sorted(config["members"]))
    return lines


def all_lines(now):
    return guild_lines(now) + hub_lines(now)
