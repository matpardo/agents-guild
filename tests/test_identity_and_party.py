from guild import db, events, identity, paths, timeutil
from tests.testutil import GuildTestCase


class ResolveActorTests(GuildTestCase):
    def _conn(self):
        return db.connect(paths.db_path())

    def test_no_session_is_human(self):
        party, unbound = identity.resolve_actor(self._conn(), None)
        self.assertEqual((party, unbound), (None, False))
        self.assertEqual(identity.actor_label(party, unbound), "human")

    def test_bound_session_is_its_party(self):
        self.run_cli(["party", "start", "alpha", "--reason", "test reason"], "sess-1", None)
        party, unbound = identity.resolve_actor(self._conn(), "sess-1")
        self.assertEqual((party, unbound), ("alpha", False))
        self.assertEqual(identity.actor_label(party, unbound), "alpha")

    def test_unbound_session_is_unbound(self):
        party, unbound = identity.resolve_actor(self._conn(), "sess-9")
        self.assertEqual((party, unbound), (None, True))
        self.assertEqual(identity.actor_label(party, unbound), "unbound session")


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
        code, out, err = self.run_cli(["party", "start", "alpha", "--reason", "test reason"], "sess-1", None)
        self.assertEqual(code, 0)
        code, out, err = self.run_cli(["whoami"], "sess-1", None)
        self.assertIn("party: alpha", out)
        self.assertIn("generation: 1", out)

    def test_start_records_session_name_from_claude_sessions_dir(self):
        self.write_session(4242, "sess-1", "2026-01-10-billing")
        self.run_cli(["party", "start", "alpha", "--reason", "test reason"], "sess-1", None)
        code, out, err = self.run_cli(["board"], None, None)
        self.assertIn("2026-01-10-billing", out)

    def test_start_requires_session(self):
        code, out, err = self.run_cli(["party", "start", "alpha", "--reason", "test reason"], None, None)
        self.assertEqual(code, 1)
        self.assertIn("requires a Claude Code session", err)

    def test_start_rejects_duplicate_name(self):
        self.run_cli(["party", "start", "alpha", "--reason", "test reason"], "sess-1", None)
        code, out, err = self.run_cli(["party", "start", "alpha", "--reason", "test reason"], "sess-2", None)
        self.assertEqual(code, 1)
        self.assertIn("already exists", err)

    def test_resume_binds_new_session_as_next_generation(self):
        self.run_cli(["party", "start", "alpha", "--reason", "test reason"], "sess-1", None)
        code, out, err = self.run_cli(["party", "resume", "alpha"], "sess-2", None)
        self.assertEqual(code, 0)
        self.assertIn("generation 2", out)
        code, out, err = self.run_cli(["whoami"], "sess-1", None)
        self.assertIn("party: (unbound)", out)
        code, out, err = self.run_cli(["whoami"], "sess-2", None)
        self.assertIn("party: alpha", out)
        self.assertIn("generation: 2", out)

    def test_resume_prints_previous_handoff_and_next_line(self):
        repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha", "--reason", "test reason"], "sess-1", repo_dir)
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", repo_dir)
        self.run_cli(["task", "add", "demo/T01", "--title", "First"], "sess-1", repo_dir)
        self.run_cli(
            ["handoff", "--in-flight", "shipping T01", "--learned", "watch ci flakes"],
            "sess-1", repo_dir,
        )
        code, out, err = self.run_cli(["party", "resume", "alpha"], "sess-2", repo_dir)
        self.assertEqual(code, 0)
        self.assertIn("shipping T01", out)
        self.assertIn("watch ci flakes", out)
        self.assertIn("task demo/T01", out)
        self.assertIn("end of guild handoff", out)

    def test_resume_without_prior_handoff_has_no_handoff_section(self):
        repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha", "--reason", "test reason"], "sess-1", repo_dir)
        code, out, err = self.run_cli(["party", "resume", "alpha"], "sess-2", repo_dir)
        self.assertEqual(code, 0)
        self.assertNotIn("Handoff", out)

    def test_resume_by_session_name_from_human_terminal(self):
        repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha", "--reason", "test reason"], "sess-1", repo_dir)
        self.write_session(4242, "sess-2", "alpha-g2")
        code, out, err = self.run_cli(
            ["party", "resume", "alpha", "--session", "alpha-g2"], None, repo_dir
        )
        self.assertEqual(code, 0)
        self.assertIn("generation 2", out)
        code, out, err = self.run_cli(["whoami"], "sess-2", None)
        self.assertIn("party: alpha", out)
        self.assertIn("generation: 2", out)

    def test_resume_by_session_name_unknown_name_fails(self):
        self.run_cli(["party", "start", "alpha", "--reason", "test reason"], "sess-1", None)
        code, out, err = self.run_cli(
            ["party", "resume", "alpha", "--session", "ghost-session"], None, None
        )
        self.assertEqual(code, 1)
        self.assertIn("no session named 'ghost-session'", err)

    def test_resume_by_session_name_inside_claude_session_fails(self):
        self.run_cli(["party", "start", "alpha", "--reason", "test reason"], "sess-1", None)
        self.write_session(4242, "sess-2", "alpha-g2")
        code, out, err = self.run_cli(
            ["party", "resume", "alpha", "--session", "alpha-g2"], "sess-3", None
        )
        self.assertEqual(code, 1)
        self.assertIn("cannot be used from inside a Claude Code session", err)

    def test_resume_unknown_party_fails(self):
        code, out, err = self.run_cli(["party", "resume", "ghost"], "sess-1", None)
        self.assertEqual(code, 1)
        self.assertIn("unknown party", err)

    def test_resume_closed_party_fails(self):
        self.run_cli(["party", "start", "alpha", "--reason", "test reason"], "sess-1", None)
        self.run_cli(["party", "close", "--pending", "none"], "sess-1", None)
        code, out, err = self.run_cli(["party", "resume", "alpha"], "sess-2", None)
        self.assertEqual(code, 1)
        self.assertIn("closed", err)

    def test_bound_session_cannot_start_second_party(self):
        self.run_cli(["party", "start", "alpha", "--reason", "test reason"], "sess-1", None)
        code, out, err = self.run_cli(["party", "start", "beta", "--reason", "test reason"], "sess-1", None)
        self.assertEqual(code, 1)
        self.assertIn("session already leads party 'alpha'", err)
        code, out, err = self.run_cli(["whoami"], "sess-1", None)
        self.assertIn("party: alpha", out)

    def test_bound_session_cannot_resume_another_party(self):
        self.run_cli(["party", "start", "alpha", "--reason", "test reason"], "sess-1", None)
        self.run_cli(["party", "start", "beta", "--reason", "test reason"], "sess-2", None)
        code, out, err = self.run_cli(["party", "resume", "beta"], "sess-1", None)
        self.assertEqual(code, 1)
        self.assertIn("session already leads party 'alpha'", err)
        code, out, err = self.run_cli(["whoami"], "sess-1", None)
        self.assertIn("party: alpha", out)

    def test_resume_by_session_name_refuses_bound_session(self):
        self.write_session(4243, "sess-1", "alpha-g1")
        self.run_cli(["party", "start", "alpha", "--reason", "test reason"], "sess-1", None)
        self.run_cli(["party", "start", "beta", "--reason", "test reason"], "sess-2", None)
        code, out, err = self.run_cli(["party", "resume", "beta", "--session", "alpha-g1"], None, None)
        self.assertEqual(code, 1)
        self.assertIn("session already leads party 'alpha'", err)

    def test_leader_resumes_own_party(self):
        self.run_cli(["party", "start", "alpha", "--reason", "test reason"], "sess-1", None)
        code, out, err = self.run_cli(["party", "resume", "alpha"], "sess-1", None)
        self.assertEqual(code, 0, err)
        self.assertIn("generation 2", out)

    def test_close_requires_binding(self):
        code, out, err = self.run_cli(["party", "close", "--pending", "none"], "sess-1", None)
        self.assertEqual(code, 1)
        self.assertIn("session not bound", err)

    def test_close_unbinds_party(self):
        self.run_cli(["party", "start", "alpha", "--reason", "test reason"], "sess-1", None)
        code, out, err = self.run_cli(["party", "close", "--pending", "none"], "sess-1", None)
        self.assertEqual(code, 0)
        code, out, err = self.run_cli(["whoami"], "sess-1", None)
        self.assertIn("party: (unbound)", out)


class PartyNameValidationTests(GuildTestCase):
    def test_start_rejects_path_traversal_name(self):
        code, out, err = self.run_cli(["party", "start", "../../tmp/x", "--reason", "test reason"], "sess-1", None)
        self.assertEqual(code, 1)
        self.assertIn("invalid party name", err)

    def test_start_rejects_slash_in_name(self):
        code, out, err = self.run_cli(["party", "start", "a/b", "--reason", "test reason"], "sess-1", None)
        self.assertEqual(code, 1)
        self.assertIn("invalid party name", err)

    def test_resume_rejects_path_traversal_name(self):
        code, out, err = self.run_cli(["party", "resume", "../../tmp/x"], "sess-1", None)
        self.assertEqual(code, 1)
        self.assertIn("invalid party name", err)


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


class DoubleBindingTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha", "--reason", "test reason"], "sess-1", self.repo_dir)
        self.run_cli(["party", "start", "beta", "--reason", "test reason"], "sess-2", self.repo_dir)
        self.conn = db.connect(paths.db_path())
        with db.writing(self.conn):
            events.record(
                self.conn, timeutil.utcnow(), "test@host", "beta", "sess-1", "acme",
                "party.resumed", "local", {"party": "beta", "generation": 2, "session_name": None},
            )

    def test_binding_is_the_most_recent_leadership(self):
        for _ in range(5):
            self.assertEqual(identity.resolve_binding(self.conn, "sess-1")["party"], "beta")

    def test_doctor_reports_double_binding(self):
        code, out, err = self.run_cli(["doctor"], None, None)
        self.assertIn("warn    session leads 2 active parties: alpha, beta", out)

    def test_drift_reports_double_binding(self):
        code, out, err = self.run_cli(["drift"], "sess-1", self.repo_dir)
        self.assertIn("session leads several parties (1)", out)
        self.assertIn("session leads 2 active parties: alpha, beta", out)
