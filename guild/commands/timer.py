import subprocess

from guild import timeutil
from guild.errors import GuildError

_SERVICE_NAME = "guild-sync-gh.service"
_TIMER_NAME = "guild-sync-gh.timer"
_PRINT_HINT = "run `guild sync-timer print` and install the units by hand"

_SERVICE_TEMPLATE = """[Unit]
Description=guild sync --source gh

[Service]
Type=oneshot
ExecStart={executable} sync --source gh
"""

_TIMER_TEMPLATE = """[Unit]
Description=Run guild sync --source gh periodically

[Timer]
OnBootSec=2m
OnUnitActiveSec={seconds}s
Unit={service}

[Install]
WantedBy=timers.target
"""


def run_systemctl(argv):
    result = subprocess.run(argv, capture_output=True, text=True)
    return result.returncode, result.stderr


def _require_executable(guild_executable):
    if guild_executable is None:
        raise GuildError("`guild` executable not found on PATH", 1)
    return guild_executable


def _require_systemd(platform, systemctl_available, hint):
    if platform != "linux":
        raise GuildError("systemd user units are only supported on Linux; {}".format(hint), 1)
    if not systemctl_available:
        raise GuildError("systemctl not found; {}".format(hint), 1)


def _systemctl(runner, arguments):
    returncode, stderr = runner(["systemctl", "--user"] + arguments)
    if returncode != 0:
        raise GuildError("systemctl --user {} failed: {}".format(" ".join(arguments), stderr.strip()), 1)


def render_units(guild_executable, every):
    seconds = int(timeutil.parse_duration(every).total_seconds())
    service = _SERVICE_TEMPLATE.format(executable=_require_executable(guild_executable))
    timer = _TIMER_TEMPLATE.format(seconds=seconds, service=_SERVICE_NAME)
    return service, timer


def print_units(guild_executable, every):
    service, timer = render_units(guild_executable, every)
    return "# {}\n{}\n# {}\n{}".format(_SERVICE_NAME, service, _TIMER_NAME, timer)


def install(unit_dir, guild_executable, every, runner, platform, systemctl_available):
    _require_systemd(platform, systemctl_available, _PRINT_HINT)
    service, timer = render_units(guild_executable, every)
    unit_dir.mkdir(parents=True, exist_ok=True)
    (unit_dir / _SERVICE_NAME).write_text(service)
    (unit_dir / _TIMER_NAME).write_text(timer)
    _systemctl(runner, ["daemon-reload"])
    _systemctl(runner, ["enable", "--now", _TIMER_NAME])
    return "installed {} (every {}) in {}".format(_TIMER_NAME, every, unit_dir)


def uninstall(unit_dir, runner, platform, systemctl_available):
    _require_systemd(platform, systemctl_available, "remove the units by hand")
    _systemctl(runner, ["disable", "--now", _TIMER_NAME])
    (unit_dir / _SERVICE_NAME).unlink(missing_ok=True)
    (unit_dir / _TIMER_NAME).unlink(missing_ok=True)
    _systemctl(runner, ["daemon-reload"])
    return "uninstalled {} from {}".format(_TIMER_NAME, unit_dir)
