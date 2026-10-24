import json
import re

from guild import names, paths
from guild.errors import GuildError
from guild.realm import client, hubconfig

_KEYS = frozenset(("url", "fingerprint", "guild", "token"))
_FINGERPRINT_RE = re.compile(r"(?:[0-9A-F]{2}:){31}[0-9A-F]{2}")


def exists():
    return paths.realm_config_path().exists()


def normalize_fingerprint(raw):
    fingerprint = raw.strip().upper()
    if _FINGERPRINT_RE.fullmatch(fingerprint) is None:
        raise GuildError("invalid fingerprint: expected 32 colon-separated hex bytes (SHA-256)", 1)
    return fingerprint


def problems(config):
    if not isinstance(config, dict) or set(config) != _KEYS:
        return ["keys must be exactly url, fingerprint, guild, token"]
    found = [
        "{} must be a non-empty string".format(key)
        for key in sorted(_KEYS)
        if not isinstance(config[key], str) or not config[key]
    ]
    if found:
        return found
    try:
        client.parse_url(config["url"])
        normalize_fingerprint(config["fingerprint"])
        names.validate_name(config["guild"], "guild name")
    except GuildError as error:
        return [error.message]
    return []


def load():
    path = paths.realm_config_path()
    if not path.exists():
        raise GuildError("no realm config: run `guild realm join` first", 1)
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        raise GuildError("realm config is not valid JSON: {}".format(path), 1)
    found = problems(config)
    if found:
        raise GuildError("realm config is malformed: {}".format(found[0]), 1)
    return config


def save(config):
    path = paths.realm_config_path()
    paths.ensure_private_dir(path.parent)
    hubconfig.write_atomic(path, (json.dumps(config, indent=2, sort_keys=True) + "\n").encode("utf-8"))
