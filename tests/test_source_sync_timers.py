import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from guild.adapters import jira_acli
from guild.commands import timer as timer_commands
from tests.testutil import GuildTestCase

_PATTERNS = {
    "task_heading": r"^#{2,3}\s+(T\d+\w*)\b.*?\s[—–-]\s+(.+)$",
    "key_ref": r"[A-Z][A-Z0-9]*-\d+",
    "deps_line": r"^\*\*Deps:\*\*\s*(.+)$",
    "status_line": r"^\*\*Status:\*\*\s*(.+)$",
}


class _RecordingRunner:
    def __init__(self):
        self.calls = []

    def __call__(self, argv):
        self.calls.append(argv)
        return 0, ""


class SourceSyncUnitTests(unittest.TestCase):
    def test_sdd_service_syncs_every_project(self):
        service, timer = timer_commands.render_units(timer_commands.SYNC_SDD, "/opt/bin/guild", "10m")
        self.assertIn("ExecStart=/opt/bin/guild sync --source sdd --all-projects\n", service)
        self.assertIn("Unit=guild-sync-sdd.service", timer)
        self.assertIn("OnUnitActiveSec=600s", timer)

    def test_tracker_service_syncs_every_project(self):
        service, timer = timer_commands.render_units(timer_commands.SYNC_TRACKER, "/opt/bin/guild", "30m")
        self.assertIn("ExecStart=/opt/bin/guild sync --source tracker --all-projects\n", service)
        self.assertIn("Unit=guild-sync-tracker.service", timer)

    def test_install_and_uninstall_touch_only_their_own_units(self):
        with tempfile.TemporaryDirectory() as directory:
            unit_dir = Path(directory)
            runner = _RecordingRunner()
            timer_commands.install(timer_commands.SYNC_SDD, unit_dir, "/opt/bin/guild", "10m", runner, "linux", True)
            timer_commands.install(
                timer_commands.SYNC_TRACKER, unit_dir, "/opt/bin/guild", "10m", runner, "linux", True
            )
            self.assertEqual(
                sorted(path.name for path in unit_dir.iterdir()),
                [
                    "guild-sync-sdd.service",
                    "guild-sync-sdd.timer",
                    "guild-sync-tracker.service",
                    "guild-sync-tracker.timer",
                ],
            )
            timer_commands.uninstall(timer_commands.SYNC_SDD, unit_dir, runner, "linux", True)
            self.assertEqual(
                sorted(path.name for path in unit_dir.iterdir()),
                ["guild-sync-tracker.service", "guild-sync-tracker.timer"],
            )

    def test_missing_acli_is_a_query_error_not_a_crash(self):
        with mock.patch("subprocess.run", side_effect=FileNotFoundError("acli")):
            with self.assertRaises(jira_acli.JiraAcliError):
                jira_acli.children_of("DEMO-1")


class SourceSyncTimerCliTests(GuildTestCase):
    def test_print_renders_exec_start(self):
        with mock.patch("shutil.which", return_value="/opt/bin/guild"):
            code, out, err = self.run_cli(["sync-tracker-timer", "print", "--every", "10m"], None, None)
        self.assertEqual(code, 0, err)
        self.assertIn("ExecStart=/opt/bin/guild sync --source tracker --all-projects", out)

    def test_install_goes_through_the_runner(self):
        runner = _RecordingRunner()
        with mock.patch("shutil.which", return_value="/opt/bin/guild"):
            with mock.patch.object(timer_commands, "run_systemctl", runner):
                code, out, err = self.run_cli(["sync-sdd-timer", "install", "--every", "10m"], None, None)
        self.assertEqual(code, 0, err)
        self.assertTrue((self.config_home / "systemd" / "user" / "guild-sync-sdd.timer").exists())
        self.assertEqual(len(runner.calls), 2)


class AllProjectsSyncTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.projects_dir = self.config_home / "guild" / "projects"
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        self.sdd_root = self.root / "sdd-docs"
        epic_dir = self.sdd_root / "epics" / "widget"
        epic_dir.mkdir(parents=True)
        (epic_dir / "tasks.md").write_text("## T01 — One\n\n**Deps:** —\n**Status:** [ ] pending\n")
        self._write_project("bare", {})
        self._write_project("withsdd", {"sdd": dict(_PATTERNS, root=str(self.sdd_root), epics_dir="epics")})

    def _write_project(self, name, extra):
        data = {"name": name, "paths": [str(self.root / name) + "/*"], "github": {"repos": []}}
        data.update(extra)
        (self.projects_dir / (name + ".json")).write_text(json.dumps(data))

    def _sync(self, source):
        return self.run_cli(["sync", "--source", source, "--all-projects"], None, self.root)

    def test_projects_without_a_tracker_are_skipped_cleanly(self):
        code, out, err = self._sync("tracker")
        self.assertEqual(code, 0, err)
        self.assertEqual(err, "")

    def test_projects_without_sdd_are_skipped_and_others_sync(self):
        code, out, err = self._sync("sdd")
        self.assertEqual(code, 0, err)
        self.assertEqual(err, "")

    def test_no_projects_at_all_is_a_clean_run(self):
        for path in self.projects_dir.glob("*.json"):
            path.unlink()
        code, out, err = self._sync("sdd")
        self.assertEqual(code, 0, err)

    def test_a_broken_project_is_reported_with_its_name(self):
        self._write_project("broken", {"sdd": dict(_PATTERNS, root=str(self.root / "nowhere"), epics_dir="epics")})
        code, out, err = self._sync("sdd")
        self.assertEqual(code, 1)
        self.assertIn("broken:", err)

    def test_tracker_project_without_cards_makes_no_query(self):
        self._write_project("withtracker", {"tracker": {"kind": "jira-acli"}})
        code, out, err = self._sync("tracker")
        self.assertEqual(code, 0, err)

    def test_all_projects_rejects_gh(self):
        code, out, err = self._sync("gh")
        self.assertEqual(code, 1)
        self.assertIn("--all-projects", err)


if __name__ == "__main__":
    unittest.main()
