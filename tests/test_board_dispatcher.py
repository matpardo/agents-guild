from datetime import timedelta
from pathlib import Path

from guild import timeutil
from guild.commands import board as board_commands
from tests.test_web_board_model import BoardModelTestCase


class DispatcherBoardTests(BoardModelTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha"], "sess-1", self.repo_dir)

    def _insert(self, key, party, state, age):
        ctx = self._ctx()
        decided_at = timeutil.to_iso(ctx.now - age)
        ctx.conn.execute(
            "INSERT INTO dispatch_decisions (project, key, mode, rule, outcome, party, generation,"
            " subject, reason, decided_at, state) VALUES ('acme', ?, 'on', 'next_task', 'launching', ?, 2,"
            " 'acme/app#7', ?, ?, ?)",
            (key, party, "no tmux" if state == "failed" else None, decided_at, state),
        )
        ctx.conn.commit()

    def _board(self, party_filter):
        return "\n".join(board_commands.render_board(self._ctx(), party_filter, None, False, 100))

    def test_in_flight_launch_is_shown(self):
        self._insert("a", "alpha", "launched", timedelta(minutes=5))
        model = board_commands.board_model(self._ctx())["dispatcher"]
        self.assertEqual([row["party"] for row in model["in_flight"]], ["alpha"])
        self.assertEqual(model["in_flight"][0]["age"], "5m")
        self.assertEqual(model["failed"], [])
        self.assertIn("in flight: alpha g2 launched 5m ago (next_task, acme/app#7)", self._board(None))

    def test_bound_launch_is_not_shown(self):
        self._insert("a", "alpha", "bound", timedelta(minutes=5))
        self.assertEqual(board_commands.board_model(self._ctx())["dispatcher"], {"in_flight": [], "failed": []})
        self.assertNotIn("DISPATCHER", self._board(None))

    def test_recent_failure_is_shown_with_its_reason(self):
        self._insert("a", "alpha", "failed", timedelta(hours=23))
        model = board_commands.board_model(self._ctx())["dispatcher"]
        self.assertEqual([row["reason"] for row in model["failed"]], ["no tmux"])
        self.assertIn("failed: alpha g2 23h ago (next_task): no tmux", self._board(None))

    def test_old_failure_is_hidden(self):
        self._insert("a", "alpha", "failed", timedelta(hours=25))
        self.assertEqual(board_commands.board_model(self._ctx())["dispatcher"]["failed"], [])
        self.assertNotIn("DISPATCHER", self._board(None))

    def test_party_filter_keeps_only_that_party(self):
        self._insert("a", "alpha", "launched", timedelta(minutes=1))
        self._insert("b", "beta", "launched", timedelta(minutes=1))
        model = board_commands.dispatcher_model(self._ctx(), {"alpha"})
        self.assertEqual([row["party"] for row in model["in_flight"]], ["alpha"])

    def test_web_page_has_a_dispatcher_section_fed_by_the_model(self):
        web_dir = Path(board_commands.__file__).resolve().parent.parent / "web"
        self.assertIn('id="dispatcher"', (web_dir / "index.html").read_text())
        self.assertIn("renderDispatcher(filtered.dispatcher)", (web_dir / "app.js").read_text())
