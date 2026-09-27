from tests.testutil import GuildTestCase


class AskTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha"], "sess-1", self.repo_dir)
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", self.repo_dir)
        self.run_cli(["task", "add", "demo/T01", "--title", "First"], "sess-1", self.repo_dir)

    def test_create_requires_at_least_one_ref(self):
        code, out, err = self.run_cli(
            ["ask", "ready?", "--context", "x"], "sess-1", self.repo_dir
        )
        self.assertEqual(code, 1)
        self.assertIn("at least one --ref", err)

    def test_create_rejects_unknown_task_ref(self):
        code, out, err = self.run_cli(
            ["ask", "ready?", "--context", "x", "--ref", "task:demo/T99"], "sess-1", self.repo_dir
        )
        self.assertEqual(code, 1)
        self.assertIn("does not match a known task", err)

    def test_create_and_list(self):
        code, out, err = self.run_cli(
            [
                "ask", "ready to merge?", "--context", "checks green",
                "--ref", "task:demo/T01", "--option", "yes", "--option", "no",
            ],
            "sess-1", self.repo_dir,
        )
        self.assertEqual(code, 0)
        self.assertIn("ask #1 created", out)
        code, out, err = self.run_cli(["asks"], None, None)
        self.assertIn("#1 [alpha] ready to merge?", out)
        self.assertIn("options: yes, no", out)

    def test_answer_by_human(self):
        self.run_cli(
            ["ask", "ready?", "--context", "x", "--ref", "task:demo/T01"], "sess-1", self.repo_dir
        )
        code, out, err = self.run_cli(["answer", "1", "yes, go ahead"], None, None)
        self.assertEqual(code, 0)
        code, out, err = self.run_cli(["asks"], None, None)
        self.assertEqual(out, "")

    def test_cannot_answer_twice(self):
        self.run_cli(
            ["ask", "ready?", "--context", "x", "--ref", "task:demo/T01"], "sess-1", self.repo_dir
        )
        self.run_cli(["answer", "1", "yes"], None, None)
        code, out, err = self.run_cli(["answer", "1", "again"], None, None)
        self.assertEqual(code, 1)
        self.assertIn("not open", err)

    def test_dismiss(self):
        self.run_cli(
            ["ask", "ready?", "--context", "x", "--ref", "task:demo/T01"], "sess-1", self.repo_dir
        )
        code, out, err = self.run_cli(["dismiss", "1"], None, None)
        self.assertEqual(code, 0)
        code, out, err = self.run_cli(["asks"], None, None)
        self.assertEqual(out, "")

    def test_unknown_ask_id(self):
        code, out, err = self.run_cli(["answer", "42", "x"], None, None)
        self.assertEqual(code, 1)
        self.assertIn("unknown ask", err)


if __name__ == "__main__":
    import unittest

    unittest.main()
