from guild import paths, statusline_state
from tests.testutil import GuildTestCase


class RecordAndReadCtxTests(GuildTestCase):
    def test_read_ctx_returns_none_when_never_recorded(self):
        self.assertIsNone(statusline_state.read_ctx(paths.state_dir(), "sess-1"))

    def test_read_ctx_returns_recorded_value(self):
        statusline_state.record_ctx(paths.state_dir(), "sess-1", 42)
        self.assertEqual(statusline_state.read_ctx(paths.state_dir(), "sess-1"), 42)


class StatuslineTests(GuildTestCase):
    def test_ctx_flag_persists_pct_and_leaves_render_unchanged(self):
        code, out, err = self.run_cli(["statusline", "--session", "sess-1", "--ctx", "81"], None, None)
        self.assertEqual(code, 0)
        self.assertEqual(out, "")
        ctx_file = paths.state_dir() / "ctx" / "sess-1"
        self.assertEqual(ctx_file.read_text(), "81")

    def test_ctx_flag_keeps_the_first_nonzero_pct_as_baseline(self):
        for pct in ("0", "12", "30"):
            self.run_cli(["statusline", "--session", "sess-1", "--ctx", pct], None, None)
        self.assertEqual((paths.state_dir() / "ctx-baseline" / "sess-1").read_text(), "12")

    def test_empty_when_nothing_pending(self):
        code, out, err = self.run_cli(["statusline", "--session", "sess-1"], None, None)
        self.assertEqual(code, 0)
        self.assertEqual(out, "")

    def test_shows_open_asks_and_notices(self):
        repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha", "--reason", "test reason"], "sess-1", repo_dir)
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", repo_dir)
        self.run_cli(["task", "add", "demo/T01", "--title", "First"], "sess-1", repo_dir)
        self.run_cli(["ask", "ready?", "--context", "x", "--ref", "task:demo/T01"], "sess-1", repo_dir)
        self.run_cli(["notice", "create", "pipeline down", "--to", "guild", "--ttl", "2h"], None, None)

        code, out, err = self.run_cli(["statusline", "--session", "sess-1"], None, None)
        self.assertEqual(code, 0)
        self.assertIn("1 asks", out)
        self.assertIn("1 notice", out)


class StatuslineIdentityTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha", "--reason", "test reason"], "sess-1", self.repo_dir)

    def _statusline(self, session):
        code, out, err = self.run_cli(["statusline", "--session", session], None, None)
        self.assertEqual(code, 0)
        return out.strip()

    def test_solo_bound_shows_generation_only(self):
        self.assertEqual(self._statusline("sess-1"), "g1")

    def test_solo_bound_appends_pending_parts_after_generation(self):
        self.run_cli(["notice", "create", "pipeline down", "--to", "guild", "--ttl", "2h"], None, None)
        self.assertEqual(self._statusline("sess-1"), "g1 · 1 notice")

    def test_member_shows_raid_name(self):
        self.run_cli(["raid", "join", "infra", "--ttl", "2h"], "sess-1", self.repo_dir)
        self.assertEqual(self._statusline("sess-1"), "⚔ infra · g1")

    def test_paused_raid_shows_pause_marker(self):
        self.run_cli(["raid", "join", "infra", "--ttl", "2h"], "sess-1", self.repo_dir)
        self.run_cli(["raid", "pause", "infra"], "sess-1", self.repo_dir)
        self.assertEqual(self._statusline("sess-1"), "⚔ infra ⏸ · g1")

    def test_multiple_raids_are_sorted_and_comma_joined(self):
        self.run_cli(["raid", "join", "zeta", "--ttl", "2h"], "sess-1", self.repo_dir)
        self.run_cli(["raid", "join", "infra", "--ttl", "2h"], "sess-1", self.repo_dir)
        self.assertEqual(self._statusline("sess-1"), "⚔ infra, zeta · g1")

    def test_unbound_session_is_unchanged(self):
        self.assertEqual(self._statusline("sess-unbound"), "")


if __name__ == "__main__":
    import unittest

    unittest.main()


class StatuslineBlockedTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha", "--reason", "test reason"], "sess-1", self.repo_dir)
        self.run_cli(["party", "start", "beta", "--reason", "test reason"], "sess-2", self.repo_dir)

    def _block(self, session_id):
        self.run_hook(
            "notification",
            {
                "session_id": session_id,
                "cwd": str(self.repo_dir),
                "notification_type": "permission_prompt",
                "message": "x",
            },
        )

    def _statusline(self, session):
        code, out, err = self.run_cli(["statusline", "--session", session], None, None)
        self.assertEqual(code, 0)
        return out.strip()

    def test_omitted_when_nobody_blocked(self):
        self.assertNotIn("blocked", self._statusline("sess-1"))

    def test_counts_blocked_parties(self):
        self._block("sess-2")
        self.assertEqual(self._statusline("sess-1"), "g1 · ⏸1 blocked")
        self._block("sess-1")
        self.assertEqual(self._statusline("sess-1"), "g1 · ⏸2 blocked")

    def test_closed_party_not_counted(self):
        self._block("sess-2")
        self.run_cli(["party", "close", "--pending", "none"], "sess-2", self.repo_dir)
        self.assertNotIn("blocked", self._statusline("sess-1"))


class UnsafeSessionIdTests(GuildTestCase):
    def test_traversal_session_id_stays_inside_the_state_dir(self):
        state_dir = paths.state_dir()
        statusline_state.record_ctx(state_dir, "../../escaped", 42)
        statusline_state.record_baseline_once(state_dir, "../../escaped", 42)
        self.assertEqual(statusline_state.read_ctx(state_dir, "../../escaped"), 42)
        self.assertFalse((state_dir.parent / "escaped").exists())
        self.assertFalse((state_dir.parent.parent / "escaped").exists())
        self.assertEqual(len(list((state_dir / "ctx").iterdir())), 1)
        self.assertNotIn("escaped", [path.name for path in (state_dir / "ctx").iterdir()])
