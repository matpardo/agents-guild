from guild import db, events
from guild.cli import _build_context
from guild.commands import rebuild as rebuild_commands
from tests.testutil import GuildTestCase


def _decided(mode, outcome, key):
    return {
        "project": "acme",
        "rule": "ask_answered",
        "key": key,
        "mode": mode,
        "outcome": outcome,
        "party": "alpha",
        "generation": 5,
        "permission_mode": "acceptEdits",
        "subject": "ask #12",
        "reason": None,
    }


class DispatchStateTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.ctx = _build_context(None, self.root)

    def tearDown(self):
        self.ctx.conn.close()
        super().tearDown()

    def _record(self, kind, payload):
        with db.writing(self.ctx.conn):
            return events.record(
                self.ctx.conn, self.ctx.now, self.ctx.origin, "alpha", None, "acme", kind, "local", payload
            )

    def _rows(self):
        return [
            dict(row)
            for row in self.ctx.conn.execute("SELECT * FROM dispatch_decisions ORDER BY key, mode").fetchall()
        ]

    def test_launching_decision_row_starts_in_launching_state(self):
        self._record("dispatch.decided", _decided("on", "launching", "ask_answered:12"))
        row = self._rows()[0]
        self.assertEqual(row["project"], "acme")
        self.assertEqual(row["outcome"], "launching")
        self.assertEqual(row["state"], "launching")
        self.assertEqual(row["party"], "alpha")
        self.assertEqual(row["generation"], 5)
        self.assertEqual(row["permission_mode"], "acceptEdits")
        self.assertEqual(row["subject"], "ask #12")
        self.assertEqual(row["decided_at"], self.ctx.conn.execute("SELECT ts FROM events").fetchone()["ts"])
        self.assertIsNone(row["window_id"])

    def test_planned_and_skipped_decisions_have_no_state(self):
        self._record("dispatch.decided", _decided("dry-run", "planned", "ask_answered:12"))
        skipped = _decided("on", "skipped", "ask_answered:13")
        skipped["reason"] = "party closed"
        self._record("dispatch.decided", skipped)
        rows = self._rows()
        self.assertEqual([row["state"] for row in rows], [None, None])
        self.assertEqual(rows[1]["reason"], "party closed")

    def test_launched_then_bound_transitions(self):
        self._record("dispatch.decided", _decided("on", "launching", "ask_answered:12"))
        self._record(
            "dispatch.launched",
            {"project": "acme", "key": "ask_answered:12", "party": "alpha", "generation": 5, "window_id": "@12"},
        )
        row = self._rows()[0]
        self.assertEqual((row["state"], row["window_id"]), ("launched", "@12"))
        self._record(
            "dispatch.bound",
            {"project": "acme", "key": "ask_answered:12", "party": "alpha", "generation": 5},
        )
        self.assertEqual(self._rows()[0]["state"], "bound")

    def test_launch_failed_records_reason_and_window(self):
        self._record("dispatch.decided", _decided("on", "launching", "ask_answered:12"))
        self._record(
            "dispatch.launch_failed",
            {
                "project": "acme",
                "key": "ask_answered:12",
                "party": "alpha",
                "generation": 5,
                "reason": "window exited before binding",
                "window_id": "@12",
            },
        )
        row = self._rows()[0]
        self.assertEqual(row["state"], "failed")
        self.assertEqual(row["reason"], "window exited before binding")
        self.assertEqual(row["window_id"], "@12")

    def test_dry_run_and_real_decision_on_same_key_coexist(self):
        self._record("dispatch.decided", _decided("dry-run", "planned", "ask_answered:12"))
        self._record("dispatch.decided", _decided("on", "launching", "ask_answered:12"))
        self.assertEqual([row["mode"] for row in self._rows()], ["dry-run", "on"])

    def test_transitions_touch_only_the_real_decision(self):
        self._record("dispatch.decided", _decided("dry-run", "planned", "ask_answered:12"))
        self._record("dispatch.decided", _decided("on", "launching", "ask_answered:12"))
        self._record(
            "dispatch.bound",
            {"project": "acme", "key": "ask_answered:12", "party": "alpha", "generation": 5},
        )
        self.assertEqual([row["state"] for row in self._rows()], [None, "bound"])

    def test_rebuild_reproduces_decisions_and_keeps_cursors(self):
        self._record("dispatch.decided", _decided("dry-run", "planned", "ask_answered:12"))
        self._record("dispatch.decided", _decided("on", "launching", "ask_answered:12"))
        self._record(
            "dispatch.launched",
            {"project": "acme", "key": "ask_answered:12", "party": "alpha", "generation": 5, "window_id": "@12"},
        )
        self.ctx.conn.execute("INSERT INTO dispatch_cursors (project, last_seq) VALUES ('acme', 77)")
        before = self._rows()
        rebuild_commands.run(self.ctx)
        self.assertEqual(self._rows(), before)
        cursor = self.ctx.conn.execute("SELECT last_seq FROM dispatch_cursors WHERE project = 'acme'").fetchone()
        self.assertEqual(cursor["last_seq"], 77)
