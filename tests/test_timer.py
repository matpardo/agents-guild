from unittest import mock

from guild import paths
from guild.commands import timer as timer_commands
from guild.errors import GuildError
from tests.testutil import GuildTestCase


class _RecordingRunner:
    def __init__(self, returncode, stderr):
        self.calls = []
        self._returncode = returncode
        self._stderr = stderr

    def __call__(self, argv):
        self.calls.append(argv)
        return self._returncode, self._stderr


class TimerTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.unit_dir = self.root / "units"

    def test_render_units_embeds_executable_and_interval(self):
        service, timer = timer_commands.render_units(timer_commands.SYNC_GH, "/opt/bin/guild", "15m")
        self.assertIn("ExecStart=/opt/bin/guild sync --source gh", service)
        self.assertIn("Type=oneshot", service)
        self.assertIn("OnUnitActiveSec=900s", timer)
        self.assertIn("Unit=guild-sync-gh.service", timer)
        self.assertIn("WantedBy=timers.target", timer)

    def test_render_units_rejects_invalid_duration(self):
        with self.assertRaises(GuildError) as raised:
            timer_commands.render_units(timer_commands.SYNC_GH, "/opt/bin/guild", "soon")
        self.assertIn("invalid duration", raised.exception.message)

    def test_install_writes_units_and_enables_timer(self):
        runner = _RecordingRunner(0, "")
        message = timer_commands.install(
            timer_commands.SYNC_GH, self.unit_dir, "/opt/bin/guild", "15m", runner, "linux", True
        )
        self.assertTrue((self.unit_dir / "guild-sync-gh.service").exists())
        self.assertIn("OnUnitActiveSec=900s", (self.unit_dir / "guild-sync-gh.timer").read_text())
        self.assertEqual(
            runner.calls,
            [
                ["systemctl", "--user", "daemon-reload"],
                ["systemctl", "--user", "enable", "--now", "guild-sync-gh.timer"],
            ],
        )
        self.assertIn("guild-sync-gh.timer", message)

    def test_install_fails_off_linux_and_suggests_print(self):
        runner = _RecordingRunner(0, "")
        with self.assertRaises(GuildError) as raised:
            timer_commands.install(
                timer_commands.SYNC_GH, self.unit_dir, "/opt/bin/guild", "15m", runner, "darwin", True
            )
        self.assertIn("guild sync-timer print", raised.exception.message)
        self.assertEqual(runner.calls, [])
        self.assertFalse(self.unit_dir.exists())

    def test_install_fails_without_systemctl_and_suggests_print(self):
        runner = _RecordingRunner(0, "")
        with self.assertRaises(GuildError) as raised:
            timer_commands.install(
                timer_commands.SYNC_GH, self.unit_dir, "/opt/bin/guild", "15m", runner, "linux", False
            )
        self.assertIn("guild sync-timer print", raised.exception.message)
        self.assertFalse(self.unit_dir.exists())

    def test_install_validates_duration_before_writing(self):
        runner = _RecordingRunner(0, "")
        with self.assertRaises(GuildError):
            timer_commands.install(timer_commands.SYNC_GH, self.unit_dir, "/opt/bin/guild", "x", runner, "linux", True)
        self.assertFalse(self.unit_dir.exists())

    def test_install_reports_systemctl_failure(self):
        runner = _RecordingRunner(1, "boom")
        with self.assertRaises(GuildError) as raised:
            timer_commands.install(
                timer_commands.SYNC_GH, self.unit_dir, "/opt/bin/guild", "15m", runner, "linux", True
            )
        self.assertIn("boom", raised.exception.message)

    def test_uninstall_disables_and_removes_units(self):
        timer_commands.install(
            timer_commands.SYNC_GH, self.unit_dir, "/opt/bin/guild", "15m", _RecordingRunner(0, ""), "linux", True
        )
        runner = _RecordingRunner(0, "")
        timer_commands.uninstall(timer_commands.SYNC_GH, self.unit_dir, runner, "linux", True)
        self.assertFalse((self.unit_dir / "guild-sync-gh.service").exists())
        self.assertFalse((self.unit_dir / "guild-sync-gh.timer").exists())
        self.assertEqual(
            runner.calls,
            [
                ["systemctl", "--user", "disable", "--now", "guild-sync-gh.timer"],
                ["systemctl", "--user", "daemon-reload"],
            ],
        )

    def test_uninstall_fails_off_linux(self):
        with self.assertRaises(GuildError) as raised:
            timer_commands.uninstall(timer_commands.SYNC_GH, self.unit_dir, _RecordingRunner(0, ""), "darwin", True)
        self.assertIn("systemd", raised.exception.message)


class TimerCliTests(GuildTestCase):
    def test_print_outputs_units_without_writing(self):
        with mock.patch("shutil.which", return_value="/opt/bin/guild"):
            exit_code, stdout, _ = self.run_cli(["sync-timer", "print", "--every", "10m"], None, None)
        self.assertEqual(exit_code, 0)
        self.assertIn("guild-sync-gh.service", stdout)
        self.assertIn("OnUnitActiveSec=600s", stdout)
        self.assertFalse((self.config_home / "systemd").exists())

    def test_print_rejects_invalid_duration(self):
        exit_code, _, stderr = self.run_cli(["sync-timer", "print", "--every", "nope"], None, None)
        self.assertEqual(exit_code, 1)
        self.assertIn("invalid duration", stderr)

    def test_install_requires_every(self):
        exit_code, _, _ = self.run_cli(["sync-timer", "install"], None, None)
        self.assertEqual(exit_code, 2)

    def test_install_off_linux_fails_with_hint(self):
        with mock.patch("sys.platform", "darwin"):
            exit_code, _, stderr = self.run_cli(["sync-timer", "install", "--every", "10m"], None, None)
        self.assertEqual(exit_code, 1)
        self.assertIn("guild sync-timer print", stderr)
        self.assertFalse((self.config_home / "systemd").exists())

    def test_systemd_user_dir_follows_xdg_config_home(self):
        self.assertEqual(paths.systemd_user_dir(), self.config_home / "systemd" / "user")
