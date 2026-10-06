import json

from guild import context, db, paths, timeutil
from guild.commands import board as board_commands
from tests.testutil import GuildTestCase

_OPEN_VIEW = {"state": "OPEN", "isDraft": False, "headRefName": "feature/x", "title": "t"}


class CardPrViewsTestCase(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        config_file = self.config_home / "guild" / "projects" / "acme.json"
        data = json.loads(config_file.read_text())
        data["tracker"] = {"browse_url": "https://tracker.example/browse/"}
        config_file.write_text(json.dumps(data))
        self.run_cli(["party", "start", "alpha"], "sess-1", self.repo_dir)
        self.write_gh_fixture("view_acme-app_1", _OPEN_VIEW)
        code, out, err = self.run_cli(
            ["pr", "track", "acme/app#1", "--card", "ABC-123", "--what", "fix ci", "--waits", "review"],
            "sess-1", self.repo_dir,
        )
        self.assertEqual(code, 0, err)

    def _model(self):
        conn = db.connect(paths.db_path())
        ctx = context.RunContext(
            conn, None, None, timeutil.utcnow(), None,
            paths.claude_sessions_dir(), paths.projects_config_dir(), paths.state_dir(),
        )
        try:
            return board_commands.board_model(ctx)
        finally:
            conn.close()


class CardPrBoardTests(CardPrViewsTestCase):
    def test_cli_board_lists_the_card_under_prs_outside_active_tasks(self):
        code, out, err = self.run_cli(["board"], None, None)
        self.assertIn("PRs outside active tasks", out)
        self.assertIn("ABC-123", out)
        self.assertIn("fix ci", out)

    def test_web_model_exposes_card_and_card_url(self):
        pr_model = self._model()["parties"][0]["prs"][0]
        self.assertEqual(pr_model["card"], "ABC-123")
        self.assertEqual(pr_model["card_url"], "https://tracker.example/browse/ABC-123")

    def test_web_model_has_no_card_for_a_task_pr(self):
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", self.repo_dir)
        self.run_cli(["task", "add", "demo/T01", "--title", "First"], "sess-1", self.repo_dir)
        self.run_cli(["task", "start", "demo/T01"], "sess-1", self.repo_dir)
        self.write_gh_fixture("view_acme-app_2", _OPEN_VIEW)
        self.run_cli(
            ["pr", "track", "acme/app#2", "--task", "demo/T01", "--what", "x", "--waits", "y"],
            "sess-1", self.repo_dir,
        )
        task_prs = self._model()["parties"][0]["quests"][0]["tasks"][0]["prs"]
        self.assertIsNone(task_prs[0]["card"])
        self.assertIsNone(task_prs[0]["card_url"])


class CardPrQueueTests(CardPrViewsTestCase):
    def test_merge_queue_cli_shows_the_card_in_the_task_column(self):
        self.run_cli(["pr", "set", "acme/app#1", "--lifecycle", "ready"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["merge-queue"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        self.assertIn("ABC-123", out)

    def test_web_merge_queue_entry_task_is_the_card(self):
        self.run_cli(["pr", "set", "acme/app#1", "--lifecycle", "ready"], "sess-1", self.repo_dir)
        queue = self._model()["merge_queues"][0]["queue"]
        self.assertEqual(queue[0]["task"], "ABC-123")


class CardPrNextTests(CardPrViewsTestCase):
    def test_failing_checks_of_a_card_pr_are_reported(self):
        self.write_gh_fixture(
            "view_acme-app_1", dict(_OPEN_VIEW, statusCheckRollup=[{"conclusion": "FAILURE"}])
        )
        self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["next"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        self.assertIn("PR acme/app#1: failing checks (1 failing)", out)


if __name__ == "__main__":
    import unittest

    unittest.main()
