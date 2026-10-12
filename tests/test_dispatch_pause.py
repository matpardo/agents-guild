import sqlite3

from tests.testutil import GuildTestCase


class DispatchPauseTestCase(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha"], "sess-1", self.repo_dir)

    def _pause_row(self):
        conn = sqlite3.connect(str(self.data_home / "guild" / "guild.db"))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM dispatch_pause").fetchone()
        conn.close()
        return row


class PauseResumeCommandTests(DispatchPauseTestCase):
    def test_human_pauses_without_a_session(self):
        code, out, err = self.run_cli(["dispatch", "pause", "--reason", "deploy freeze"], None, None)
        self.assertEqual(code, 0, err)
        self.assertIn("dispatch paused: deploy freeze", out)
        row = self._pause_row()
        self.assertEqual((row["paused_by"], row["reason"]), ("human", "deploy freeze"))

    def test_bound_session_pauses_as_its_party(self):
        code, out, err = self.run_cli(["dispatch", "pause", "--reason", "incident"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        self.assertEqual(self._pause_row()["paused_by"], "alpha")

    def test_unbound_session_pauses_as_session(self):
        code, out, err = self.run_cli(["dispatch", "pause", "--reason", "incident"], "sess-9", self.repo_dir)
        self.assertEqual(code, 0, err)
        self.assertEqual(self._pause_row()["paused_by"], "unbound session")

    def test_pause_twice_fails(self):
        self.run_cli(["dispatch", "pause", "--reason", "incident"], None, None)
        code, out, err = self.run_cli(["dispatch", "pause", "--reason", "again"], None, None)
        self.assertEqual(code, 1)
        self.assertIn("dispatch is already paused", err)

    def test_empty_reason_rejected(self):
        code, out, err = self.run_cli(["dispatch", "pause", "--reason", "  "], None, None)
        self.assertEqual(code, 1)
        self.assertIn("must not be empty", err)
        self.assertIsNone(self._pause_row())

    def test_overlong_reason_rejected(self):
        code, out, err = self.run_cli(["dispatch", "pause", "--reason", "x" * 301], None, None)
        self.assertEqual(code, 1)
        self.assertIn("exceeds the maximum length", err)
        self.assertIsNone(self._pause_row())

    def test_reason_with_an_email_is_rejected(self):
        code, out, err = self.run_cli(["dispatch", "pause", "--reason", "ping a@b.com"], None, None)
        self.assertEqual(code, 1)
        self.assertIn("must not contain an email address", err)
        self.assertIsNone(self._pause_row())

    def test_resume_works_from_a_terminal(self):
        self.run_cli(["dispatch", "pause", "--reason", "incident"], None, None)
        code, out, err = self.run_cli(["dispatch", "resume"], None, None)
        self.assertEqual(code, 0, err)
        self.assertIn("dispatch resumed", out)
        self.assertIsNone(self._pause_row())

    def test_resume_from_a_session_fails(self):
        self.run_cli(["dispatch", "pause", "--reason", "incident"], None, None)
        code, out, err = self.run_cli(["dispatch", "resume"], "sess-1", self.repo_dir)
        self.assertEqual(code, 1)
        self.assertIn("dispatch resume must be run by a human, outside a session", err)
        self.assertIsNotNone(self._pause_row())

    def test_resume_when_not_paused_fails(self):
        code, out, err = self.run_cli(["dispatch", "resume"], None, None)
        self.assertEqual(code, 1)
        self.assertIn("dispatch is not paused", err)

    def test_rebuild_reproduces_pause(self):
        self.run_cli(["dispatch", "pause", "--reason", "incident"], None, None)
        code, out, err = self.run_cli(["rebuild"], None, None)
        self.assertEqual(code, 0, err)
        self.assertEqual(self._pause_row()["reason"], "incident")

    def test_rebuild_reproduces_resume(self):
        self.run_cli(["dispatch", "pause", "--reason", "incident"], None, None)
        self.run_cli(["dispatch", "resume"], None, None)
        self.run_cli(["rebuild"], None, None)
        self.assertIsNone(self._pause_row())


class StatusVisibilityTests(DispatchPauseTestCase):
    def test_status_shows_paused_line(self):
        self.run_cli(["dispatch", "pause", "--reason", "incident"], None, None)
        code, out, err = self.run_cli(["dispatch", "status"], None, None)
        self.assertEqual(code, 0, err)
        self.assertIn("PAUSED since", out)
        self.assertIn("by human: incident", out)

    def test_status_shows_paused_line_with_no_dispatcher_configured(self):
        self.run_cli(["dispatch", "pause", "--reason", "incident"], None, None)
        code, out, err = self.run_cli(["dispatch", "status"], None, None)
        self.assertEqual(code, 0, err)
        self.assertIn("PAUSED since", out)
        self.assertIn("dispatcher not configured", out)

    def test_status_has_no_paused_line_when_running(self):
        code, out, err = self.run_cli(["dispatch", "status"], None, None)
        self.assertEqual(code, 0, err)
        self.assertNotIn("PAUSED", out)


class ParserTests(DispatchPauseTestCase):
    def test_pause_requires_a_reason(self):
        code, out, err = self.run_cli(["dispatch", "pause"], None, None)
        self.assertNotEqual(code, 0)
        self.assertIn("--reason", err)
        self.assertIsNone(self._pause_row())

    def test_resume_takes_no_arguments(self):
        code, out, err = self.run_cli(["dispatch", "resume", "--reason", "x"], None, None)
        self.assertNotEqual(code, 0)


if __name__ == "__main__":
    import unittest

    unittest.main()
