from tests.testutil import GuildTestCase


class BriefTests(GuildTestCase):
    def test_unbound_shows_hint(self):
        code, out, err = self.run_cli(["brief"], "sess-1", None)
        self.assertEqual(code, 0)
        self.assertIn("session not bound", out)

    def test_human_terminal_points_to_board(self):
        code, out, err = self.run_cli(["brief"], None, None)
        self.assertEqual(code, 0)
        self.assertNotIn("session not bound", out)
        self.assertIn("guild board", out)
        self.assertIn("guild asks", out)

    def test_bound_shows_quest_and_prs(self):
        repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha"], "sess-1", repo_dir)
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", repo_dir)
        self.run_cli(["task", "add", "demo/T01", "--title", "First"], "sess-1", repo_dir)
        self.run_cli(["task", "start", "demo/T01"], "sess-1", repo_dir)
        code, out, err = self.run_cli(["brief"], "sess-1", repo_dir)
        self.assertEqual(code, 0)
        self.assertIn("quest: demo", out)
        self.assertIn("active: T01", out)


class InboxTests(GuildTestCase):
    def test_new_notice_from_other_party_appears_once(self):
        repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha"], "sess-1", repo_dir)
        self.run_cli(["party", "start", "beta"], "sess-2", repo_dir)
        self.run_cli(["notice", "create", "pipeline down", "--to", "guild", "--ttl", "2h"], None, None)

        code, out, err = self.run_cli(["inbox", "--since-last"], "sess-2", repo_dir)
        self.assertEqual(code, 0)
        self.assertIn("pipeline down", out)

        code, out, err = self.run_cli(["inbox", "--since-last"], "sess-2", repo_dir)
        self.assertEqual(out, "")

    def test_closed_notice_not_delivered(self):
        repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "beta"], "sess-2", repo_dir)
        self.run_cli(["notice", "create", "pipeline down", "--to", "guild", "--ttl", "2h"], None, None)
        self.run_cli(["notice", "close", "1"], None, None)

        code, out, err = self.run_cli(["inbox", "--since-last"], "sess-2", repo_dir)
        self.assertEqual(out, "")

    def test_own_partys_notice_not_in_own_inbox(self):
        repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha"], "sess-1", repo_dir)
        code, out, err = self.run_cli(
            ["notice", "create", "fyi", "--to", "guild", "--ttl", "2h"], "sess-1", repo_dir
        )
        code, out, err = self.run_cli(["inbox", "--since-last"], "sess-1", repo_dir)
        self.assertEqual(out, "")

    def test_answer_reaches_asking_partys_inbox(self):
        repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha"], "sess-1", repo_dir)
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", repo_dir)
        self.run_cli(["task", "add", "demo/T01", "--title", "First"], "sess-1", repo_dir)
        self.run_cli(
            ["ask", "ready?", "--context", "x", "--ref", "task:demo/T01"], "sess-1", repo_dir
        )
        self.run_cli(["inbox", "--since-last"], "sess-1", repo_dir)
        self.run_cli(["answer", "1", "yes go"], None, None)

        code, out, err = self.run_cli(["inbox", "--since-last"], "sess-1", repo_dir)
        self.assertIn("ask #1 answered: yes go", out)


class BoardTests(GuildTestCase):
    def test_board_filters_by_party(self):
        repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha"], "sess-1", repo_dir)
        self.run_cli(["party", "start", "beta"], "sess-2", repo_dir)
        code, out, err = self.run_cli(["board", "--party", "alpha"], None, None)
        self.assertIn("━━ alpha", out)
        self.assertNotIn("━━ beta", out)

    def test_board_puts_open_asks_first_with_answer_hint(self):
        repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha"], "sess-1", repo_dir)
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", repo_dir)
        self.run_cli(["task", "add", "demo/T01", "--title", "First"], "sess-1", repo_dir)
        self.run_cli(
            ["ask", "Ship it?", "--context", "tests green", "--ref", "task:demo/T01",
             "--option", "yes", "--option", "no"],
            "sess-1", repo_dir,
        )
        code, out, err = self.run_cli(["board"], None, None)
        self.assertEqual(code, 0)
        self.assertLess(out.index("NEEDS YOU · 1 open ask"), out.index("━━ alpha"))
        self.assertIn("#1 alpha · Ship it?  [yes | no]", out)
        self.assertNotIn("tests green", out)
        self.assertIn("guild asks", out)

    def test_board_nests_pr_under_its_task(self):
        repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha"], "sess-1", repo_dir)
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", repo_dir)
        self.run_cli(["task", "add", "demo/T01", "--title", "First"], "sess-1", repo_dir)
        self.run_cli(["task", "start", "demo/T01", "--summary", "coding"], "sess-1", repo_dir)
        self.write_gh_fixture(
            "view_acme-app_1",
            {"state": "OPEN", "isDraft": True, "headRefName": "feature/x", "title": "t"},
        )
        self.run_cli(
            ["pr", "track", "acme/app#1", "--task", "demo/T01", "--what", "Adds X", "--waits", "review"],
            "sess-1", repo_dir,
        )
        code, out, err = self.run_cli(["board"], None, None)
        lines = out.splitlines()
        task_index = next(i for i, line in enumerate(lines) if "▶ T01" in line)
        self.assertIn("First", lines[task_index])
        self.assertIn("coding", lines[task_index + 1])
        self.assertIn("app#1  draft", lines[task_index + 2])
        self.assertIn("Adds X", lines[task_index + 2])
        self.assertIn("waits: review", lines[task_index + 3])

    def test_board_without_asks_says_nothing_needs_you(self):
        repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha"], "sess-1", repo_dir)
        code, out, err = self.run_cli(["board"], None, None)
        self.assertIn("NEEDS YOU · nothing", out)


if __name__ == "__main__":
    import unittest

    unittest.main()
