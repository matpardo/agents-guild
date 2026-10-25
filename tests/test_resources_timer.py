import tempfile
import unittest
from pathlib import Path
from unittest import mock

from guild.commands import timer as timer_commands
from guild.errors import GuildError
from tests.testutil import GuildTestCase

_SYNC_GOLDEN = (
    "# guild-sync-gh.service\n[Unit]\nDescription=guild sync --source gh\n\n[Service]\nType=oneshot\n"
    "ExecStart=/opt/bin/guild sync --source gh\n\n# guild-sync-gh.timer\n[Unit]\n"
    "Description=Run guild sync --source gh periodically\n\n[Timer]\nOnBootSec=2m\n"
    "OnUnitActiveSec=900s\nUnit=guild-sync-gh.service\n\n[Install]\nWantedBy=timers.target\n"
)


class _RecordingRunner:
    def __init__(self):
        self.calls = []

    def __call__(self, argv):
        self.calls.append(argv)
        return 0, ""


class SyncTimerGoldenTests(unittest.TestCase):
    def test_sync_units_are_byte_identical_to_the_original_rendering(self):
        self.assertEqual(timer_commands.print_units(timer_commands.SYNC_GH, "/opt/bin/guild", "15m"), _SYNC_GOLDEN)

    def test_sync_service_has_no_scheduling_options(self):
        service, _ = timer_commands.render_units(timer_commands.SYNC_GH, "/opt/bin/guild", "15m")
        self.assertNotIn("Nice=", service)
        self.assertNotIn("IOSchedulingClass", service)


class ResourcesUnitTests(unittest.TestCase):
    def test_service_runs_collect_at_lowest_cpu_and_idle_io_priority(self):
        service, _ = timer_commands.render_units(timer_commands.RESOURCES_COLLECT, "/opt/bin/guild", "2h")
        self.assertEqual(
            service,
            "[Unit]\nDescription=guild resources collect\n\n[Service]\nType=oneshot\n"
            "Nice=19\nIOSchedulingClass=idle\nExecStart=/opt/bin/guild resources collect\n",
        )

    def test_timer_fires_at_the_requested_interval_for_its_own_service(self):
        _, timer = timer_commands.render_units(timer_commands.RESOURCES_COLLECT, "/opt/bin/guild", "2h")
        self.assertIn("OnUnitActiveSec=7200s", timer)
        self.assertIn("Unit=guild-resources-collect.service", timer)
        self.assertIn("Description=Run guild resources collect periodically", timer)

    def test_print_names_both_units(self):
        text = timer_commands.print_units(timer_commands.RESOURCES_COLLECT, "/opt/bin/guild", "2h")
        self.assertIn("# guild-resources-collect.service", text)
        self.assertIn("# guild-resources-collect.timer", text)

    def test_rejects_invalid_duration(self):
        with self.assertRaises(GuildError):
            timer_commands.render_units(timer_commands.RESOURCES_COLLECT, "/opt/bin/guild", "soon")

    def test_install_writes_only_its_own_units_and_enables_its_timer(self):
        with tempfile.TemporaryDirectory() as directory:
            unit_dir = Path(directory) / "units"
            runner = _RecordingRunner()
            message = timer_commands.install(
                timer_commands.RESOURCES_COLLECT, unit_dir, "/opt/bin/guild", "2h", runner, "linux", True
            )
            self.assertEqual(
                sorted(path.name for path in unit_dir.iterdir()),
                ["guild-resources-collect.service", "guild-resources-collect.timer"],
            )
            self.assertEqual(
                runner.calls,
                [
                    ["systemctl", "--user", "daemon-reload"],
                    ["systemctl", "--user", "enable", "--now", "guild-resources-collect.timer"],
                ],
            )
            self.assertIn("guild-resources-collect.timer", message)

    def test_install_hint_points_to_the_resources_timer(self):
        with self.assertRaises(GuildError) as raised:
            timer_commands.install(
                timer_commands.RESOURCES_COLLECT,
                mock.Mock(),
                "/opt/bin/guild",
                "2h",
                _RecordingRunner(),
                "darwin",
                True,
            )
        self.assertIn("guild resources-timer print", raised.exception.message)

    def test_uninstall_removes_only_its_own_units(self):
        with tempfile.TemporaryDirectory() as directory:
            unit_dir = Path(directory)
            timer_commands.install(
                timer_commands.SYNC_GH, unit_dir, "/opt/bin/guild", "15m", _RecordingRunner(), "linux", True
            )
            timer_commands.install(
                timer_commands.RESOURCES_COLLECT, unit_dir, "/opt/bin/guild", "2h", _RecordingRunner(), "linux", True
            )
            runner = _RecordingRunner()
            timer_commands.uninstall(timer_commands.RESOURCES_COLLECT, unit_dir, runner, "linux", True)
            self.assertEqual(
                sorted(path.name for path in unit_dir.iterdir()),
                ["guild-sync-gh.service", "guild-sync-gh.timer"],
            )
            self.assertEqual(
                runner.calls,
                [
                    ["systemctl", "--user", "disable", "--now", "guild-resources-collect.timer"],
                    ["systemctl", "--user", "daemon-reload"],
                ],
            )


class ResourcesTimerCliTests(GuildTestCase):
    def test_print_outputs_units_without_writing(self):
        with mock.patch("shutil.which", return_value="/opt/bin/guild"):
            code, out, err = self.run_cli(["resources-timer", "print", "--every", "2h"], None, None)
        self.assertEqual(code, 0, err)
        self.assertIn("ExecStart=/opt/bin/guild resources collect", out)
        self.assertIn("OnUnitActiveSec=7200s", out)
        self.assertFalse((self.config_home / "systemd").exists())

    def test_install_requires_every(self):
        code, _, _ = self.run_cli(["resources-timer", "install"], None, None)
        self.assertEqual(code, 2)

    def test_install_off_linux_fails_with_hint_and_writes_nothing(self):
        with mock.patch("sys.platform", "darwin"):
            code, _, err = self.run_cli(["resources-timer", "install", "--every", "2h"], None, None)
        self.assertEqual(code, 1)
        self.assertIn("guild resources-timer print", err)
        self.assertFalse((self.config_home / "systemd").exists())

    def test_install_writes_units_in_the_xdg_dir_through_the_runner(self):
        runner = _RecordingRunner()
        with mock.patch("shutil.which", return_value="/opt/bin/guild"):
            with mock.patch.object(timer_commands, "run_systemctl", runner):
                code, out, err = self.run_cli(["resources-timer", "install", "--every", "2h"], None, None)
        self.assertEqual(code, 0, err)
        unit_dir = self.config_home / "systemd" / "user"
        self.assertTrue((unit_dir / "guild-resources-collect.timer").exists())
        self.assertEqual(len(runner.calls), 2)

    def test_uninstall_goes_through_the_runner(self):
        runner = _RecordingRunner()
        with mock.patch("shutil.which", return_value="/usr/bin/systemctl"):
            with mock.patch.object(timer_commands, "run_systemctl", runner):
                code, out, err = self.run_cli(["resources-timer", "uninstall"], None, None)
        self.assertEqual(code, 0, err)
        self.assertEqual(runner.calls[0][-1], "guild-resources-collect.timer")


if __name__ == "__main__":
    unittest.main()
