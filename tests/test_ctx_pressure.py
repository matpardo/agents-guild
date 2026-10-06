import os

from guild import context, ctx_pressure, db, paths, timeutil
from guild.commands import statusline as statusline_commands
from tests.testutil import GuildTestCase


class ThresholdTests(GuildTestCase):
    def test_no_project_config_uses_the_default(self):
        self.assertEqual(ctx_pressure.threshold(None), ctx_pressure.DEFAULT_HANDOFF_THRESHOLD)

    def test_project_without_the_key_uses_the_default(self):
        self.assertEqual(ctx_pressure.threshold({"name": "acme"}), ctx_pressure.DEFAULT_HANDOFF_THRESHOLD)

    def test_project_value_wins(self):
        self.assertEqual(ctx_pressure.threshold({"name": "acme", "handoff_threshold": 40}), 40)

    def test_default_is_eighty(self):
        self.assertEqual(ctx_pressure.DEFAULT_HANDOFF_THRESHOLD, 80)


class IsHighTests(GuildTestCase):
    def test_equal_to_the_threshold_is_high(self):
        self.assertTrue(ctx_pressure.is_high(40, {"handoff_threshold": 40}))

    def test_below_the_threshold_is_not_high(self):
        self.assertFalse(ctx_pressure.is_high(39, {"handoff_threshold": 40}))

    def test_default_threshold_applies_without_config(self):
        self.assertTrue(ctx_pressure.is_high(80, None))
        self.assertFalse(ctx_pressure.is_high(79, None))


class ReadingTests(GuildTestCase):
    def test_no_recorded_pct_is_none(self):
        self.assertIsNone(ctx_pressure.reading(paths.state_dir(), "sess-1", None))

    def test_unreadable_pct_is_none(self):
        (paths.state_dir() / "ctx").mkdir(parents=True, exist_ok=True)
        (paths.state_dir() / "ctx" / "sess-1").write_text("later")
        self.assertIsNone(ctx_pressure.reading(paths.state_dir(), "sess-1", None))

    def test_reading_carries_pct_threshold_and_high(self):
        statusline_commands.record_ctx(paths.state_dir(), "sess-1", 86)
        self.assertEqual(
            ctx_pressure.reading(paths.state_dir(), "sess-1", {"handoff_threshold": 40}),
            {"pct": 86, "threshold": 40, "high": True},
        )

    def test_reading_below_the_threshold_is_not_high(self):
        statusline_commands.record_ctx(paths.state_dir(), "sess-1", 10)
        self.assertEqual(
            ctx_pressure.reading(paths.state_dir(), "sess-1", None),
            {"pct": 10, "threshold": ctx_pressure.DEFAULT_HANDOFF_THRESHOLD, "high": False},
        )


class ForPartyTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha"], "sess-1", self.repo_dir)
        self.conn = db.connect(paths.db_path())

    def _ctx(self):
        return context.RunContext(
            self.conn, None, None, timeutil.utcnow(), None,
            paths.claude_sessions_dir(), paths.projects_config_dir(), paths.state_dir(),
        )

    def _party_row(self):
        return self.conn.execute("SELECT * FROM parties WHERE name = 'alpha'").fetchone()

    def test_live_leader_carries_its_reading(self):
        statusline_commands.record_ctx(paths.state_dir(), "sess-1", 91)
        self.write_session(os.getpid(), "sess-1", "alpha-g1")
        reading = ctx_pressure.for_party(self._ctx(), self._party_row(), None)
        self.assertEqual(reading["pct"], 91)
        self.assertTrue(reading["high"])

    def test_dead_leader_has_no_reading(self):
        statusline_commands.record_ctx(paths.state_dir(), "sess-1", 91)
        self.assertIsNone(ctx_pressure.for_party(self._ctx(), self._party_row(), None))
