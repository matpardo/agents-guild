import tempfile
import unittest
from pathlib import Path
from unittest import mock

from guild.commands import timer as timer_commands
from guild.errors import GuildError
from tests.testutil import GuildTestCase


class _RecordingRunner:
    def __init__(self):
        self.calls = []

    def __call__(self, argv):
        self.calls.append(argv)
        return 0, ""


class DispatchUnitTests(unittest.TestCase):
    def test_service_runs_dispatch_run(self):
        service, _ = timer_commands.render_units(timer_commands.DISPATCH, "/opt/bin/guild", "5m")
        self.assertEqual(
            service,
            "[Unit]\nDescription=guild dispatch run\n\n[Service]\nType=oneshot\n"
            "NoNewPrivileges=yes\nNice=10\nExecStart=/opt/bin/guild dispatch run\n",
        )

    def test_timer_fires_at_the_requested_interval_for_its_own_service(self):
        _, timer = timer_commands.render_units(timer_commands.DISPATCH, "/opt/bin/guild", "5m")
        self.assertIn("OnUnitActiveSec=300s", timer)
        self.assertIn("Unit=guild-dispatch.service", timer)

    def test_print_names_both_units(self):
        text = timer_commands.print_units(timer_commands.DISPATCH, "/opt/bin/guild", "5m")
        self.assertIn("# guild-dispatch.service", text)
        self.assertIn("# guild-dispatch.timer", text)
        self.assertIn("ExecStart=/opt/bin/guild dispatch run", text)

    def test_install_and_uninstall_touch_only_the_dispatch_units(self):
        with tempfile.TemporaryDirectory() as directory:
            unit_dir = Path(directory)
            install_runner = _RecordingRunner()
            timer_commands.install(
                timer_commands.DISPATCH, unit_dir, "/opt/bin/guild", "5m", install_runner, "linux", True
            )
            self.assertEqual(
                sorted(path.name for path in unit_dir.iterdir()), ["guild-dispatch.service", "guild-dispatch.timer"]
            )
            self.assertEqual(
                install_runner.calls,
                [
                    ["systemctl", "--user", "daemon-reload"],
                    ["systemctl", "--user", "enable", "--now", "guild-dispatch.timer"],
                ],
            )
            uninstall_runner = _RecordingRunner()
            timer_commands.uninstall(timer_commands.DISPATCH, unit_dir, uninstall_runner, "linux", True)
            self.assertEqual(list(unit_dir.iterdir()), [])
            self.assertEqual(uninstall_runner.calls[0][-1], "guild-dispatch.timer")

    def test_install_hint_points_to_the_dispatch_timer(self):
        with self.assertRaises(GuildError) as raised:
            timer_commands.install(
                timer_commands.DISPATCH, mock.Mock(), "/opt/bin/guild", "5m", _RecordingRunner(), "darwin", True
            )
        self.assertIn("guild dispatch-timer print", raised.exception.message)


class DispatchTimerCliTests(GuildTestCase):
    def test_print_renders_exec_start(self):
        with mock.patch("shutil.which", return_value="/opt/bin/guild"):
            code, out, err = self.run_cli(["dispatch-timer", "print", "--every", "5m"], None, None)
        self.assertEqual(code, 0, err)
        self.assertIn("ExecStart=/opt/bin/guild dispatch run", out)
        self.assertFalse((self.config_home / "systemd").exists())

    def test_install_goes_through_the_runner(self):
        runner = _RecordingRunner()
        with mock.patch("shutil.which", return_value="/opt/bin/guild"):
            with mock.patch.object(timer_commands, "run_systemctl", runner):
                code, out, err = self.run_cli(["dispatch-timer", "install", "--every", "5m"], None, None)
        self.assertEqual(code, 0, err)
        self.assertTrue((self.config_home / "systemd" / "user" / "guild-dispatch.timer").exists())
        self.assertEqual(len(runner.calls), 2)

    def test_uninstall_goes_through_the_runner(self):
        runner = _RecordingRunner()
        with mock.patch("shutil.which", return_value="/usr/bin/systemctl"):
            with mock.patch.object(timer_commands, "run_systemctl", runner):
                code, out, err = self.run_cli(["dispatch-timer", "uninstall"], None, None)
        self.assertEqual(code, 0, err)
        self.assertEqual(runner.calls[0][-1], "guild-dispatch.timer")


if __name__ == "__main__":
    unittest.main()
