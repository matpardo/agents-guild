import os

from guild import context, ctx_pressure, db, paths, timeutil
from guild.commands import statusline as statusline_commands
from tests.testutil import GuildTestCase


class ThresholdTests(GuildTestCase):
    def _value(self, global_config, project_config):
        return ctx_pressure.threshold(paths.state_dir(), global_config, project_config)

    def test_no_project_config_uses_the_default(self):
        self.assertEqual(self._value({}, None), {"value": 80, "source": "configured"})

    def test_project_without_the_key_uses_the_default(self):
        self.assertEqual(self._value({}, {"name": "acme"})["value"], ctx_pressure.DEFAULT_HANDOFF_THRESHOLD)

    def test_project_value_wins(self):
        self.assertEqual(self._value({}, {"name": "acme", "handoff_threshold": 40})["value"], 40)

    def test_default_is_eighty(self):
        self.assertEqual(ctx_pressure.DEFAULT_HANDOFF_THRESHOLD, 80)

    def test_margin_without_a_compaction_uses_the_configured_value(self):
        self.assertEqual(self._value({"handoff_margin": 10}, {"handoff_threshold": 70}), {"value": 70, "source": "configured"})

    def test_compaction_without_a_margin_uses_the_configured_value(self):
        statusline_commands.record_compact_pct(paths.state_dir(), 85)
        self.assertEqual(self._value({}, {"handoff_threshold": 70})["value"], 70)

    def test_margin_follows_the_latest_compaction(self):
        statusline_commands.record_compact_pct(paths.state_dir(), 30)
        statusline_commands.record_compact_pct(paths.state_dir(), 85)
        self.assertEqual(
            self._value({"handoff_margin": 10}, {"handoff_threshold": 70}),
            {"value": 75, "source": "compaction 85% − 10"},
        )

    def test_margin_is_the_same_for_every_project(self):
        statusline_commands.record_compact_pct(paths.state_dir(), 60)
        self.assertEqual(self._value({"handoff_margin": 10}, {"handoff_threshold": 20})["value"], 50)
        self.assertEqual(self._value({"handoff_margin": 10}, {"handoff_threshold": 90})["value"], 50)

    def test_margin_above_the_compaction_floors_at_zero(self):
        statusline_commands.record_compact_pct(paths.state_dir(), 5)
        self.assertEqual(self._value({"handoff_margin": 10}, None)["value"], 0)


class ReadingTests(GuildTestCase):
    def test_no_recorded_pct_is_none(self):
        self.assertIsNone(ctx_pressure.reading(paths.state_dir(), "sess-1", {}, None))

    def test_unreadable_pct_is_none(self):
        (paths.state_dir() / "ctx").mkdir(parents=True, exist_ok=True)
        (paths.state_dir() / "ctx" / "sess-1").write_text("later")
        self.assertIsNone(ctx_pressure.reading(paths.state_dir(), "sess-1", {}, None))

    def test_reading_carries_pct_threshold_source_and_high(self):
        statusline_commands.record_ctx(paths.state_dir(), "sess-1", 86)
        self.assertEqual(
            ctx_pressure.reading(paths.state_dir(), "sess-1", {}, {"handoff_threshold": 40}),
            {"pct": 86, "threshold": 40, "source": "configured", "high": True},
        )

    def test_equal_to_the_threshold_is_high(self):
        statusline_commands.record_ctx(paths.state_dir(), "sess-1", 40)
        self.assertTrue(ctx_pressure.reading(paths.state_dir(), "sess-1", {}, {"handoff_threshold": 40})["high"])

    def test_reading_below_the_threshold_is_not_high(self):
        statusline_commands.record_ctx(paths.state_dir(), "sess-1", 10)
        self.assertEqual(
            ctx_pressure.reading(paths.state_dir(), "sess-1", {}, None),
            {"pct": 10, "threshold": ctx_pressure.DEFAULT_HANDOFF_THRESHOLD, "source": "configured", "high": False},
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
        reading = ctx_pressure.for_party(self._ctx(), self._party_row(), {}, None)
        self.assertEqual(reading["pct"], 91)
        self.assertTrue(reading["high"])

    def test_dead_leader_has_no_reading(self):
        statusline_commands.record_ctx(paths.state_dir(), "sess-1", 91)
        self.assertIsNone(ctx_pressure.for_party(self._ctx(), self._party_row(), {}, None))
