from guild import db, events, session_status
from guild.cli import _build_context
from guild.commands import rebuild as rebuild_commands
from tests.testutil import GuildTestCase

_BINDING = {"party": "alpha", "project": "acme", "generation": 1}


class SessionStatusTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(
            ["party", "start", "alpha", "--reason", "test reason", "--goal", "test goal", "--done-when", "test done"],
            "sess-1",
            repo_dir,
        )
        self.ctx = _build_context("sess-1", self.root)

    def _record(self, kind, payload):
        with db.writing(self.ctx.conn):
            session_status.record_change(self.ctx, _BINDING, kind, payload)

    def test_waiting_permission_sets_row(self):
        self._record("session.waiting", session_status.waiting_payload("permission", "run ls"))
        row = session_status.current(self.ctx.conn, "sess-1")
        self.assertEqual(row["status"], "waiting-permission")
        self.assertEqual(row["detail"], "run ls")
        self.assertEqual(row["party"], "alpha")

    def test_elicitation_is_waiting_permission_and_idle_is_waiting_input(self):
        self._record("session.waiting", session_status.waiting_payload("elicitation", "pick"))
        self.assertEqual(session_status.current(self.ctx.conn, "sess-1")["status"], "waiting-permission")
        self._record("session.waiting", session_status.waiting_payload("idle", ""))
        self.assertEqual(session_status.current(self.ctx.conn, "sess-1")["status"], "waiting-input")

    def test_stopped_and_working_replace_row(self):
        self._record("session.stopped", {})
        self.assertEqual(session_status.current(self.ctx.conn, "sess-1")["status"], "stopped")
        self._record("session.working", {})
        row = session_status.current(self.ctx.conn, "sess-1")
        self.assertEqual(row["status"], "working")
        self.assertIsNone(row["detail"])
        count = self.ctx.conn.execute("SELECT COUNT(*) AS n FROM session_status").fetchone()["n"]
        self.assertEqual(count, 1)

    def test_events_are_local_and_carry_binding(self):
        self._record("session.stopped", {})
        event = events.all_events(self.ctx.conn)[-1]
        self.assertEqual(event["visibility"], "local")
        self.assertEqual(event["party"], "alpha")
        self.assertEqual(event["session_id"], "sess-1")
        self.assertEqual(event["project"], "acme")

    def test_rebuild_reproduces_rows(self):
        self._record("session.waiting", session_status.waiting_payload("permission", "run ls"))
        self._record("session.stopped", {})
        before = [dict(r) for r in self.ctx.conn.execute("SELECT * FROM session_status")]
        rebuild_commands.run(self.ctx)
        after = [dict(r) for r in self.ctx.conn.execute("SELECT * FROM session_status")]
        self.assertEqual(before, after)
        self.assertEqual(after[0]["status"], "stopped")

    def test_is_change_cases(self):
        conn = self.ctx.conn
        self.assertTrue(session_status.is_change(conn, "sess-1", "working"))
        self._record("session.working", {})
        self.assertFalse(session_status.is_change(conn, "sess-1", "working"))
        self.assertTrue(session_status.is_change(conn, "sess-1", "stopped"))

    def test_waiting_payload_sanitizes_collapses_and_truncates(self):
        payload = session_status.waiting_payload("permission", "a\x1b[31mred\x1b[0m\nline\tx" + "y" * 300)
        self.assertNotIn("\x1b", payload["message"])
        self.assertNotIn("\n", payload["message"])
        self.assertNotIn("\t", payload["message"])
        self.assertEqual(len(payload["message"]), 200)
        self.assertTrue(payload["message"].startswith("ared line x"))

    def test_waiting_payload_missing_message_is_empty(self):
        self.assertEqual(session_status.waiting_payload("idle", None)["message"], "")
