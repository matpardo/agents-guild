import re
import subprocess

from guild import timeutil
from guild.errors import GuildError

_SERVICE_TEMPLATE = """[Unit]
Description={description}

[Service]
Type=oneshot
{options}ExecStart={executable} {subcommand}
"""

_INTERVAL_RE = re.compile(r"^OnUnitActiveSec=(\d+)s$", re.MULTILINE)

_TIMER_TEMPLATE = """[Unit]
Description=Run {description} periodically

[Timer]
OnBootSec=2m
OnUnitActiveSec={seconds}s
Unit={service}

[Install]
WantedBy=timers.target
"""


class _UnitSpec:
    def __init__(self, service_name, timer_name, description, subcommand, command_name, service_options):
        self.service_name = service_name
        self.timer_name = timer_name
        self.description = description
        self.subcommand = subcommand
        self.command_name = command_name
        self.service_options = service_options


SYNC_GH = _UnitSpec(
    "guild-sync-gh.service",
    "guild-sync-gh.timer",
    "guild sync --source gh",
    "sync --source gh",
    "sync-timer",
    "",
)
SYNC_SDD = _UnitSpec(
    "guild-sync-sdd.service",
    "guild-sync-sdd.timer",
    "guild sync --source sdd",
    "sync --source sdd --all-projects",
    "sync-sdd-timer",
    "",
)
SYNC_TRACKER = _UnitSpec(
    "guild-sync-tracker.service",
    "guild-sync-tracker.timer",
    "guild sync --source tracker",
    "sync --source tracker --all-projects",
    "sync-tracker-timer",
    "",
)
RESOURCES_COLLECT = _UnitSpec(
    "guild-resources-collect.service",
    "guild-resources-collect.timer",
    "guild resources collect",
    "resources collect",
    "resources-timer",
    "Nice=19\nIOSchedulingClass=idle\n",
)
COMPACT = _UnitSpec(
    "guild-compact.service",
    "guild-compact.timer",
    "guild compact",
    "compact",
    "compact-timer",
    "Nice=19\nIOSchedulingClass=idle\n",
)
UNITS = {
    "sync-gh": SYNC_GH,
    "sync-sdd": SYNC_SDD,
    "sync-tracker": SYNC_TRACKER,
    "resources-collect": RESOURCES_COLLECT,
    "compact": COMPACT,
}


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


def _print_hint(unit):
    return "run `guild {} print` and install the units by hand".format(unit.command_name)


def _render_seconds(unit, guild_executable, seconds):
    service = _SERVICE_TEMPLATE.format(
        description=unit.description,
        options=unit.service_options,
        executable=_require_executable(guild_executable),
        subcommand=unit.subcommand,
    )
    timer = _TIMER_TEMPLATE.format(description=unit.description, seconds=seconds, service=unit.service_name)
    return service, timer


def render_units(unit, guild_executable, every):
    seconds = int(timeutil.parse_duration(every).total_seconds())
    return _render_seconds(unit, guild_executable, seconds)


def installed_state(unit, unit_dir, guild_executable):
    service_path = unit_dir / unit.service_name
    timer_path = unit_dir / unit.timer_name
    if not service_path.exists() or not timer_path.exists():
        return "missing"
    installed_timer = timer_path.read_text()
    interval = _INTERVAL_RE.search(installed_timer)
    if interval is None:
        return "drifted"
    service, timer = _render_seconds(unit, guild_executable, int(interval.group(1)))
    if service_path.read_text() == service and installed_timer == timer:
        return "current"
    return "drifted"


def print_units(unit, guild_executable, every):
    service, timer = render_units(unit, guild_executable, every)
    return "# {}\n{}\n# {}\n{}".format(unit.service_name, service, unit.timer_name, timer)


def install(unit, unit_dir, guild_executable, every, runner, platform, systemctl_available):
    _require_systemd(platform, systemctl_available, _print_hint(unit))
    service, timer = render_units(unit, guild_executable, every)
    unit_dir.mkdir(parents=True, exist_ok=True)
    (unit_dir / unit.service_name).write_text(service)
    (unit_dir / unit.timer_name).write_text(timer)
    _systemctl(runner, ["daemon-reload"])
    _systemctl(runner, ["enable", "--now", unit.timer_name])
    return "installed {} (every {}) in {}".format(unit.timer_name, every, unit_dir)


def uninstall(unit, unit_dir, runner, platform, systemctl_available):
    _require_systemd(platform, systemctl_available, "remove the units by hand")
    _systemctl(runner, ["disable", "--now", unit.timer_name])
    (unit_dir / unit.service_name).unlink(missing_ok=True)
    (unit_dir / unit.timer_name).unlink(missing_ok=True)
    _systemctl(runner, ["daemon-reload"])
    return "uninstalled {} from {}".format(unit.timer_name, unit_dir)
