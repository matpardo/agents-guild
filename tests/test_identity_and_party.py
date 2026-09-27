from tests.testutil import GuildTestCase


class WhoamiTests(GuildTestCase):
    def test_unbound_session_reports_unbound(self):
        code, out, err = self.run_cli(["whoami"], "sess-1", None)
        self.assertEqual(code, 0)
        self.assertIn("party: (unbound)", out)

    def test_human_terminal_reports_no_session(self):
        code, out, err = self.run_cli(["whoami"], None, None)
        self.assertEqual(code, 0)
        self.assertIn("(none, human)", out)


class PartyStartResumeCloseTests(GuildTestCase):
    def test_start_binds_session(self):
        code, out, err = self.run_cli(["party", "start", "alpha"], "sess-1", None)
        self.assertEqual(code, 0)
        code, out, err = self.run_cli(["whoami"], "sess-1", None)
        self.assertIn("party: alpha", out)
        self.assertIn("generation: 1", out)

    def test_start_requires_session(self):
        code, out, err = self.run_cli(["party", "start", "alpha"], None, None)
        self.assertEqual(code, 1)
        self.assertIn("requires a Claude Code session", err)

    def test_start_rejects_duplicate_name(self):
        self.run_cli(["party", "start", "alpha"], "sess-1", None)
        code, out, err = self.run_cli(["party", "start", "alpha"], "sess-2", None)
        self.assertEqual(code, 1)
        self.assertIn("already exists", err)

    def test_resume_binds_new_session_as_next_generation(self):
        self.run_cli(["party", "start", "alpha"], "sess-1", None)
        code, out, err = self.run_cli(["party", "resume", "alpha"], "sess-2", None)
        self.assertEqual(code, 0)
        self.assertIn("generation 2", out)
        code, out, err = self.run_cli(["whoami"], "sess-1", None)
        self.assertIn("party: (unbound)", out)
        code, out, err = self.run_cli(["whoami"], "sess-2", None)
        self.assertIn("party: alpha", out)
        self.assertIn("generation: 2", out)

    def test_resume_unknown_party_fails(self):
        code, out, err = self.run_cli(["party", "resume", "ghost"], "sess-1", None)
        self.assertEqual(code, 1)
        self.assertIn("unknown party", err)

    def test_resume_closed_party_fails(self):
        self.run_cli(["party", "start", "alpha"], "sess-1", None)
        self.run_cli(["party", "close"], "sess-1", None)
        code, out, err = self.run_cli(["party", "resume", "alpha"], "sess-2", None)
        self.assertEqual(code, 1)
        self.assertIn("closed", err)

    def test_close_requires_binding(self):
        code, out, err = self.run_cli(["party", "close"], "sess-1", None)
        self.assertEqual(code, 1)
        self.assertIn("session not bound", err)

    def test_close_unbinds_party(self):
        self.run_cli(["party", "start", "alpha"], "sess-1", None)
        code, out, err = self.run_cli(["party", "close"], "sess-1", None)
        self.assertEqual(code, 0)
        code, out, err = self.run_cli(["whoami"], "sess-1", None)
        self.assertIn("party: (unbound)", out)


class WriteRefusalTests(GuildTestCase):
    def test_unbound_write_is_refused_with_hint(self):
        code, out, err = self.run_cli(
            ["claim", "ci.yml", "--ttl", "30m"], "sess-unbound", None
        )
        self.assertEqual(code, 1)
        self.assertIn("session not bound", err)

    def test_human_terminal_can_create_notice(self):
        code, out, err = self.run_cli(
            ["notice", "create", "pipeline down", "--to", "guild", "--ttl", "2h"], None, None
        )
        self.assertEqual(code, 0)
        self.assertIn("notice #1 created", out)

    def test_human_terminal_cannot_create_ask(self):
        code, out, err = self.run_cli(
            ["ask", "should we merge?", "--context", "x", "--ref", "task:demo/T01"], None, None
        )
        self.assertEqual(code, 1)
        self.assertIn("session not bound", err)


if __name__ == "__main__":
    import unittest

    unittest.main()
