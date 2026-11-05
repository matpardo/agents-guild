import json

from guild import db, events, paths, timeutil
from guild.cli import _build_context
from guild.commands import adventurer as adventurer_commands
from guild.commands import hook as hook_commands
from guild.errors import GuildError
from tests.fake_tmux import FakeTmux as LaunchTmux
from tests.test_handoff_respawn import FakeTmux
from tests.testutil import GuildTestCase


class WindowCloseBase(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        config_path = self.config_home / "guild" / "projects" / "acme.json"
        data = json.loads(config_path.read_text())
        data["health_jobs"] = [{"name": "red-main", "command": "/check-main", "every": "1d"}]
        config_path.write_text(json.dumps(data))
        self.conn = db.connect(paths.db_path())

    def tearDown(self):
        self.conn.close()
        super().tearDown()

    def record_window(self, window_id):
        with db.writing(self.conn):
            events.record(
                self.conn,
                timeutil.utcnow(),
                "tester@host",
                None,
                None,
                "acme",
                "health_window.launched",
                "local",
                {"window_id": window_id},
            )

    def windows(self):
        return [row["window_id"] for row in self.conn.execute("SELECT window_id FROM health_windows").fetchall()]

    def fake(self, windows, pane_windows):
        return FakeTmux(True, windows, pane_windows, True, 0)

    def finish_adventurer(self):
        code, out, err = self.run_cli(
            ["adventurer", "start", "--job", "red-main", "--reason", "test reason"], "adv-1", self.repo_dir
        )
        self.assertEqual(code, 0, err)
        code, out, err = self.run_cli(["adventurer", "done", "--pending", "none"], "adv-1", self.repo_dir)
        self.assertEqual(code, 0, err)

    def stop(self, tmux, pane):
        ctx = _build_context("adv-1", self.repo_dir)
        self.addCleanup(ctx.conn.close)
        hook_commands.stop(ctx, tmux, pane)

    def kills(self, tmux):
        return [call for call in tmux.calls if call[0] == "kill-pane"]


class LaunchRecordsWindowTests(WindowCloseBase):
    def test_launch_records_the_created_window(self):
        tmux = LaunchTmux(True, False, {}, 0)
        ctx = _build_context(None, self.repo_dir)
        self.addCleanup(ctx.conn.close)
        adventurer_commands.launch(ctx, "red-main", tmux)
        self.assertEqual(self.windows(), ["@10"])

    def test_failed_launch_records_nothing(self):
        tmux = LaunchTmux(True, False, {}, 1)
        ctx = _build_context(None, self.repo_dir)
        self.addCleanup(ctx.conn.close)
        with self.assertRaises(GuildError):
            adventurer_commands.launch(ctx, "red-main", tmux)
        self.assertEqual(self.windows(), [])

    def test_rebuild_reproduces_records(self):
        self.record_window("@4")
        self.run_cli(["rebuild"], None, None)
        self.assertEqual(self.windows(), ["@4"])


class StopClosesWindowTests(WindowCloseBase):
    def test_done_adventurer_in_launched_window_closes_its_pane(self):
        self.record_window("@4")
        self.finish_adventurer()
        tmux = self.fake({"@4": "health-red-main"}, {"%5": "@4"})
        self.stop(tmux, "%5")
        self.assertEqual(self.kills(tmux), [["kill-pane", "-t", "%5"]])

    def test_active_adventurer_keeps_its_pane(self):
        self.record_window("@4")
        self.run_cli(["adventurer", "start", "--job", "red-main", "--reason", "test reason"], "adv-1", self.repo_dir)
        tmux = self.fake({"@4": "health-red-main"}, {"%5": "@4"})
        self.stop(tmux, "%5")
        self.assertEqual(self.kills(tmux), [])

    def test_unset_pane_keeps_everything(self):
        self.record_window("@4")
        self.finish_adventurer()
        tmux = self.fake({"@4": "health-red-main"}, {"%5": "@4"})
        self.stop(tmux, None)
        self.assertEqual(self.kills(tmux), [])

    def test_unrecorded_window_keeps_its_pane(self):
        self.finish_adventurer()
        tmux = self.fake({"@4": "health-red-main"}, {"%5": "@4"})
        self.stop(tmux, "%5")
        self.assertEqual(self.kills(tmux), [])

    def test_other_window_keeps_its_pane(self):
        self.record_window("@4")
        self.finish_adventurer()
        tmux = self.fake({"@4": "health-red-main", "@7": "shell"}, {"%5": "@7"})
        self.stop(tmux, "%5")
        self.assertEqual(self.kills(tmux), [])

    def test_window_outside_guild_session_keeps_its_pane(self):
        self.record_window("@4")
        self.finish_adventurer()
        tmux = self.fake({"@9": "other"}, {"%5": "@4"})
        self.stop(tmux, "%5")
        self.assertEqual(self.kills(tmux), [])

    def test_pane_lookup_failure_keeps_its_pane(self):
        self.record_window("@4")
        self.finish_adventurer()
        tmux = self.fake({"@4": "health-red-main"}, {})
        self.stop(tmux, "%5")
        self.assertEqual(self.kills(tmux), [])

    def test_missing_tmux_keeps_its_pane(self):
        self.record_window("@4")
        self.finish_adventurer()
        tmux = FakeTmux(False, {"@4": "health-red-main"}, {"%5": "@4"}, True, 0)
        self.stop(tmux, "%5")
        self.assertEqual(tmux.calls, [])
