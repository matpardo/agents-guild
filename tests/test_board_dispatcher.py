import json
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

    def _insert_decision(self, key, rule, outcome, mode, party, age, reason):
        ctx = self._ctx()
        decided_at = timeutil.to_iso(ctx.now - age)
        ctx.conn.execute(
            "INSERT INTO dispatch_decisions (project, key, mode, rule, outcome, party, generation,"
            " subject, reason, decided_at, state) VALUES ('acme', ?, ?, ?, ?, ?, NULL, 'acme/app#7', ?, ?, NULL)",
            (key, mode, rule, outcome, party, reason, decided_at),
        )
        ctx.conn.commit()

    def _enable_dispatcher(self, rules):
        path = self.config_home / "guild" / "projects" / "acme.json"
        data = json.loads(path.read_text())
        data["dispatcher"] = {"permission_mode": "acceptEdits", "max_launches_per_hour": 3, "rules": rules}
        path.write_text(json.dumps(data))

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
        model = board_commands.board_model(self._ctx())["dispatcher"]
        self.assertEqual((model["in_flight"], model["failed"]), ([], []))
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

    def test_promote_failure_without_launch_state_is_shown(self):
        self._insert_decision("p", "pr_promote", "failed", "on", "alpha", timedelta(hours=1), "gh down")
        model = board_commands.board_model(self._ctx())["dispatcher"]
        self.assertEqual([row["reason"] for row in model["failed"]], ["gh down"])
        self.assertIn("failed: alpha g", self._board(None))

    def test_deferred_and_recent_decisions_are_listed(self):
        self._insert_decision("d", "next_task", "deferred", "on", "alpha", timedelta(minutes=3), "live session")
        self._insert_decision("n", "limit_resume", "nudged", "on", "alpha", timedelta(minutes=9), None)
        self._insert_decision("o", "merge_head", "planned", "dry-run", "beta", timedelta(hours=30), None)
        model = board_commands.dispatcher_model(self._ctx(), None)
        self.assertEqual([(row["party"], row["reason"], row["age"]) for row in model["deferred"]], [("alpha", "live session", "3m")])
        self.assertEqual([(row["outcome"], row["rule"]) for row in model["recent"]], [("nudged", "limit_resume")])
        self.assertEqual(board_commands.dispatcher_model(self._ctx(), {"beta"})["recent"], [])
        board = self._board(None)
        self.assertIn("deferred: alpha next_task acme/app#7 3m ago: live session", board)
        self.assertIn("recent: nudged limit_resume acme/app#7 alpha 9m ago", board)

    def test_dry_run_decision_is_labeled_planned(self):
        self._insert_decision("n", "limit_resume", "nudged", "dry-run", "alpha", timedelta(minutes=9), None)
        model = board_commands.dispatcher_model(self._ctx(), None)
        self.assertEqual(model["recent"][0]["outcome"], "planned")

    def test_recent_keeps_ten_newest(self):
        for number in range(12):
            self._insert_decision(str(number), "merge_head", "notified", "on", "alpha", timedelta(minutes=number + 1), None)
        recent = board_commands.dispatcher_model(self._ctx(), None)["recent"]
        self.assertEqual([row["age"] for row in recent], ["{}m".format(n) for n in range(1, 11)])

    def test_rules_and_launch_cap_are_listed_per_project(self):
        self._enable_dispatcher({"next_task": "on", "merge_head": "dry-run"})
        self._insert("a", "alpha", "launched", timedelta(minutes=5))
        model = board_commands.dispatcher_model(self._ctx(), None)
        self.assertEqual(
            model["projects"],
            [{"name": "acme", "rules": {"merge_head": "dry-run", "next_task": "on"}, "launches_last_hour": 1, "max_launches_per_hour": 3}],
        )
        self.assertIn("acme: merge_head dry-run, next_task on | launches last hour 1/3", self._board(None))

    def test_party_filter_keeps_only_that_party(self):
        self._insert("a", "alpha", "launched", timedelta(minutes=1))
        self._insert("b", "beta", "launched", timedelta(minutes=1))
        model = board_commands.dispatcher_model(self._ctx(), {"alpha"})
        self.assertEqual([row["party"] for row in model["in_flight"]], ["alpha"])

    def test_web_page_has_a_dispatcher_section_fed_by_the_model(self):
        web_dir = Path(board_commands.__file__).resolve().parent.parent / "web"
        self.assertIn('id="dispatcher"', (web_dir / "index.html").read_text())
        self.assertIn("renderDispatcher(filtered.dispatcher)", (web_dir / "app.js").read_text())

    def test_web_renders_rules_deferred_and_recent_with_filters_keeping_all_lists(self):
        js = (Path(board_commands.__file__).resolve().parent.parent / "web" / "app.js").read_text()
        for name in ("renderDispatchProject", "renderDeferred", "renderRecent", "deferred: dispatcher.deferred.filter(keep)", "recent: dispatcher.recent.filter(keep)"):
            self.assertIn(name, js)
