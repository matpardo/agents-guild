import shutil
from pathlib import Path

from guild import config
from guild.errors import GuildError


def run(ctx, name, config_file):
    source = Path(config_file)
    if not source.is_file():
        raise GuildError("config file '{}' does not exist".format(config_file), 1)
    data = config.load_project_file(source)
    if data["name"] != name:
        raise GuildError(
            "config 'name' field ('{}') does not match '{}'".format(data["name"], name), 1
        )
    ctx.projects_dir.mkdir(parents=True, exist_ok=True)
    destination = ctx.projects_dir / "{}.json".format(name)
    shutil.copy(source, destination)
    return "project '{}' registered at {}".format(name, destination)
