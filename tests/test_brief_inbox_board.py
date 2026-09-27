from tests.testutil import GuildTestCase


class BriefTests(GuildTestCase):
    def test_unbound_shows_hint(self):
        code, out, err = self.run_cli(["brief"], "sess-1", None)
        self.assertEqual(code, 0)
        self.assertIn("session not bound", out)

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
        self.assertIn("party: alpha", out)
        self.assertNotIn("party: beta", out)


if __name__ == "__main__":
    import unittest

    unittest.main()
