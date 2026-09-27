from tests.testutil import GuildTestCase


class StatuslineTests(GuildTestCase):
    def test_empty_when_nothing_pending(self):
        code, out, err = self.run_cli(["statusline", "--session", "sess-1"], None, None)
        self.assertEqual(code, 0)
        self.assertEqual(out, "")

    def test_shows_open_asks_and_notices(self):
        repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha"], "sess-1", repo_dir)
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", repo_dir)
        self.run_cli(["task", "add", "demo/T01", "--title", "First"], "sess-1", repo_dir)
        self.run_cli(
            ["ask", "ready?", "--context", "x", "--ref", "task:demo/T01"], "sess-1", repo_dir
        )
        self.run_cli(["notice", "create", "pipeline down", "--to", "guild", "--ttl", "2h"], None, None)

        code, out, err = self.run_cli(["statusline", "--session", "sess-1"], None, None)
        self.assertEqual(code, 0)
        self.assertIn("1 asks", out)
        self.assertIn("1 notice", out)


if __name__ == "__main__":
    import unittest

    unittest.main()
