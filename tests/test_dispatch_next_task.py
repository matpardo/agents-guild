import json
import os

from guild import db, paths
from guild.cli import _build_context
from guild.commands import dispatch as dispatch_commands
from tests.fake_tmux import FakeTmux
from tests.testutil import GuildTestCase

_LAUNCHED = "acme: next_task demo/T01 -> launched alpha g2 (window @10, mode acceptEdits)"


class NextTaskTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.write_block({"next_task": "on"})
        self.run_cli(["party", "start", "alpha"], "sess-1", self.repo_dir)
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", self.repo_dir)
        self.run_cli(["task", "add", "demo/T01", "--title", "First"], "sess-1", self.repo_dir)
        self.tmux = FakeTmux(True, True, {}, 0)
        self.pushes = []
        self.run_pass()

    def write_block(self, rules):
        path = self.config_home / "guild" / "projects" / "acme.json"
        data = json.loads(path.read_text())
        data["dispatcher"] = {"permission_mode": "acceptEdits", "max_launches_per_hour": 5, "rules": rules}
        path.write_text(json.dumps(data))

    def hand_off(self):
        code, out, err = self.run_cli(["handoff", "--in-flight", "x", "--learned", "y"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)

    def run_pass(self):
        ctx = _build_context(None, self.repo_dir)
        try:
            return dispatch_commands.run(ctx, False, self.tmux, self.pushes.append)
        finally:
            ctx.conn.close()

    def decision_rows(self):
        conn = db.connect(paths.db_path())
        try:
            return [
                (row["key"], row["outcome"])
                for row in conn.execute("SELECT key, outcome FROM dispatch_decisions ORDER BY rowid").fetchall()
            ]
        finally:
            conn.close()

    def test_handed_off_party_is_launched_once_per_task(self):
        self.hand_off()
        self.assertEqual(self.run_pass(), [_LAUNCHED])
        self.assertEqual(self.run_pass(), ["nothing to dispatch"])
        self.assertEqual(len(self.tmux.launch_calls()), 1)

    def test_prompt_names_the_task_and_guild_next(self):
        self.hand_off()
        self.run_pass()
        command = self.tmux.launch_calls()[0][-1]
        self.assertTrue(
            command.endswith(
                "'Continue the work described in the guild brief. Dispatched: next task demo/T01; run guild next.'"
            )
        )

    def test_busy_party_is_deferred_once_then_launched(self):
        self.hand_off()
        self.write_session(os.getpid(), "sess-1", "alpha")
        expected = "acme: next_task demo/T01 -> deferred alpha: live session"
        self.assertEqual(self.run_pass(), [expected])
        self.assertEqual(self.run_pass(), ["nothing to dispatch"])
        self.assertEqual(self.decision_rows(), [("next_task:alpha:g1:demo/T01", "deferred")])
        (self.sessions_dir / "{}.json".format(os.getpid())).unlink()
        self.assertEqual(self.run_pass(), [_LAUNCHED])
        self.assertEqual(self.run_pass(), ["nothing to dispatch"])

    def test_a_new_handoff_on_the_same_task_wakes_the_party_again(self):
        self.hand_off()
        self.run_pass()
        code, out, err = self.run_cli(["party", "resume", "alpha"], "sess-2", self.repo_dir)
        self.assertEqual(code, 0, err)
        code, out, err = self.run_cli(["handoff", "--in-flight", "x", "--learned", "y"], "sess-2", self.repo_dir)
        self.assertEqual(code, 0, err)
        self.run_pass()
        self.assertIn(("next_task:alpha:g2:demo/T01", "deferred"), self.decision_rows())

    def test_party_that_did_not_hand_off_is_skipped(self):
        self.assertEqual(self.run_pass(), ["nothing to dispatch"])
        self.assertEqual(self.tmux.launch_calls(), [])

    def test_keeper_is_skipped(self):
        self.run_cli(["party", "start", "kay", "--keeper"], "sess-2", self.repo_dir)
        self.run_cli(["quest", "add", "kq", "--title", "K", "--no-epic"], "sess-2", self.repo_dir)
        self.run_cli(["task", "add", "kq/T01", "--title", "K"], "sess-2", self.repo_dir)
        self.run_cli(["handoff", "--in-flight", "x", "--learned", "y"], "sess-2", self.repo_dir)
        self.assertEqual(self.run_pass(), ["nothing to dispatch"])

    def test_dry_run_plans_only(self):
        self.write_block({"next_task": "dry-run"})
        self.hand_off()
        lines = self.run_pass()
        self.assertEqual(len(lines), 1)
        self.assertIn("planned: launch alpha g2 (dry-run", lines[0])
        self.assertEqual(self.tmux.launch_calls(), [])

    def test_rule_absent_from_config_launches_nothing(self):
        self.write_block({"ask_answered": "on"})
        self.hand_off()
        self.assertEqual(self.run_pass(), ["nothing to dispatch"])

    def test_paused_raid_launches_nothing(self):
        code, out, err = self.run_cli(["raid", "join", "ci", "--lead", "--ttl", "8h"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        code, out, err = self.run_cli(["raid", "pause", "ci"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        self.hand_off()
        self.assertEqual(self.run_pass(), ["nothing to dispatch"])
        self.assertEqual(self.tmux.launch_calls(), [])
