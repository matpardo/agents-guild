import json
import os
import tempfile

from guild import names, paths
from guild.errors import GuildError


def exists():
    return paths.realm_hub_config_path().exists()


def _has_valid_name(config):
    name = config.get("name")
    if not isinstance(name, str):
        return False
    try:
        names.validate_name(name, "realm name")
    except GuildError:
        return False
    return True


def load():
    path = paths.realm_hub_config_path()
    if not path.exists():
        raise GuildError("no realm hub config: run `guild realm init` first", 1)
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        raise GuildError("realm hub config is not valid JSON: {}".format(path), 1) from None
    if not isinstance(config, dict) or not isinstance(config.get("members"), dict):
        raise GuildError("realm hub config is malformed: {}".format(path), 1)
    if not _has_valid_name(config):
        raise GuildError(
            'realm hub config {} needs a valid "name": add it by hand (init refuses to run twice)'.format(path), 1
        )
    return config


def write_atomic(path, data):
    descriptor, temp_name = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".")
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
        os.replace(temp_name, path)
    except BaseException:
        os.unlink(temp_name)
        raise


def save(config):
    path = paths.realm_hub_config_path()
    paths.ensure_private_dir(path.parent)
    write_atomic(path, (json.dumps(config, indent=2, sort_keys=True) + "\n").encode("utf-8"))
