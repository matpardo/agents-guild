from datetime import timedelta

from guild import db, party_status, session_status
from guild.cli import _build_context
from tests.testutil import GuildTestCase

_BINDING = {"party": "alpha", "project": "acme", "generation": 1}


class PartyStatusTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha"], "sess-1", self.repo_dir)

    def _ctx(self):
        return _build_context("sess-1", self.repo_dir)

    def _session(self, kind, payload):
        ctx = self._ctx()
        with db.writing(ctx.conn):
            session_status.record_change(ctx, _BINDING, kind, payload)

    def _waiting(self, wait, message):
        self._session("session.waiting", session_status.waiting_payload(wait, message))

    def _derive(self):
        ctx = self._ctx()
        row = ctx.conn.execute("SELECT * FROM parties WHERE name = 'alpha'").fetchone()
        return party_status.derive(ctx, row)

    def _add_task(self):
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", self.repo_dir)
        self.run_cli(["task", "add", "demo/T01", "--title", "First"], "sess-1", self.repo_dir)

    def _ask(self):
        self.run_cli(["quest", "add", "aq", "--title", "A", "--no-epic"], "sess-1", self.repo_dir)
        self.run_cli(["task", "add", "aq/T01", "--title", "First"], "sess-1", self.repo_dir)
        self.run_cli(["task", "start", "aq/T01"], "sess-1", self.repo_dir)
        self.run_cli(["ask", "ok?", "--context", "x", "--ref", "task:aq/T01"], "sess-1", self.repo_dir)

    def test_closed(self):
        self.run_cli(["party", "close"], "sess-1", self.repo_dir)
        self.assertEqual(self._derive(), {"status": "closed", "since": None, "detail": None})

    def test_awaiting_leader(self):
        self.run_cli(["handoff", "--in-flight", "x", "--learned", "y"], "sess-1", self.repo_dir)
        self.assertEqual(self._derive(), {"status": "awaiting-leader", "since": None, "detail": None})

    def test_permission_beats_ask(self):
        self._ask()
        self._waiting("permission", "run ls")
        result = self._derive()
        self.assertEqual(result["status"], "waiting-permission")
        self.assertEqual(result["detail"], "run ls")
        self.assertIsNotNone(result["since"])

    def test_ask_while_stopped(self):
        self._ask()
        self._session("session.stopped", {})
        result = self._derive()
        self.assertEqual(result["status"], "waiting-ask")
        ask_created = self._ctx().conn.execute("SELECT created_at FROM asks").fetchone()["created_at"]
        self.assertEqual(result["since"], ask_created)

    def test_ask_with_no_session_row(self):
        self._ask()
        self.assertEqual(self._derive()["status"], "waiting-ask")

    def test_ask_while_working_is_working(self):
        self._ask()
        self._session("session.working", {})
        self.assertEqual(self._derive()["status"], "working")

    def test_waiting_input(self):
        self._waiting("idle", "")
        self.assertEqual(self._derive()["status"], "waiting-input")

    def test_stopped_with_work(self):
        self._add_task()
        self._session("session.stopped", {})
        result = self._derive()
        self.assertEqual(result["status"], "stopped-with-work")
        self.assertIsNotNone(result["since"])

    def test_stopped_without_work_is_done(self):
        self._session("session.stopped", {})
        self.assertEqual(self._derive()["status"], "done")

    def test_no_row_is_working(self):
        self.assertEqual(self._derive(), {"status": "working", "since": None, "detail": None})

    def test_stopped_with_paused_raid_is_done(self):
        self._add_task()
        self.run_cli(["raid", "join", "ci", "--until-leave", "--lead"], "sess-1", self.repo_dir)
        self.run_cli(["raid", "pause", "ci"], "sess-1", self.repo_dir)
        self._session("session.stopped", {})
        self.assertEqual(self._derive()["status"], "done")

    def test_label_with_age(self):
        self._waiting("permission", "x")
        ctx = self._ctx()
        ctx.now = ctx.now + timedelta(minutes=12, seconds=5)
        status = party_status.derive(ctx, ctx.conn.execute("SELECT * FROM parties").fetchone())
        self.assertEqual(party_status.label(ctx, status), "waiting-permission 12m")

    def test_label_without_since_is_bare_name(self):
        ctx = self._ctx()
        status = {"status": "working", "since": None, "detail": None}
        self.assertEqual(party_status.label(ctx, status), "working")
