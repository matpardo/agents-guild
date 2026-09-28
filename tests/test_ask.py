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
        self.assertIn("#1 alpha · ready to merge?", out)
        self.assertIn("options: yes | no", out)
        self.assertIn('guild answer 1 "..."', out)

    def test_answer_by_human(self):
        self.run_cli(
            ["ask", "ready?", "--context", "x", "--ref", "task:demo/T01"], "sess-1", self.repo_dir
        )
        code, out, err = self.run_cli(["answer", "1", "yes, go ahead"], None, None)
        self.assertEqual(code, 0)
        code, out, err = self.run_cli(["asks"], None, None)
        self.assertIn("NEEDS YOU · nothing", out)

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
        self.assertIn("NEEDS YOU · nothing", out)

    def test_asks_sorted_by_ref_count_desc_then_created_then_id(self):
        self.run_cli(["task", "add", "demo/T02", "--title", "Second"], "sess-1", self.repo_dir)
        self.run_cli(
            ["ask", "single ref?", "--context", "x", "--ref", "task:demo/T01"], "sess-1", self.repo_dir
        )
        self.run_cli(
            [
                "ask", "two refs?", "--context", "x",
                "--ref", "task:demo/T01", "--ref", "task:demo/T02",
            ],
            "sess-1", self.repo_dir,
        )
        code, out, err = self.run_cli(["asks"], None, None)
        self.assertLess(out.index("two refs?"), out.index("single ref?"))

    def test_unknown_ask_id(self):
        code, out, err = self.run_cli(["answer", "42", "x"], None, None)
        self.assertEqual(code, 1)
        self.assertIn("unknown ask", err)

    def test_create_prints_broadcast_reminder(self):
        code, out, err = self.run_cli(
            ["ask", "ready?", "--context", "x", "--ref", "task:demo/T01"], "sess-1", self.repo_dir
        )
        self.assertEqual(code, 0)
        self.assertIn("guild: this text is broadcast to every session", out)

    def test_create_rejects_question_over_max_length(self):
        code, out, err = self.run_cli(
            ["ask", "x" * 301, "--context", "x", "--ref", "task:demo/T01"], "sess-1", self.repo_dir
        )
        self.assertEqual(code, 1)
        self.assertIn("exceeds the maximum length", err)

    def test_create_rejects_context_over_max_length(self):
        code, out, err = self.run_cli(
            ["ask", "ready?", "--context", "x" * 2001, "--ref", "task:demo/T01"], "sess-1", self.repo_dir
        )
        self.assertEqual(code, 1)
        self.assertIn("exceeds the maximum length", err)

    def test_create_rejects_email_in_question(self):
        code, out, err = self.run_cli(
            ["ask", "reach jane.doe@example.com?", "--context", "x", "--ref", "task:demo/T01"],
            "sess-1", self.repo_dir,
        )
        self.assertEqual(code, 1)
        self.assertIn("must not contain an email address", err)

    def test_answer_rejects_text_over_max_length(self):
        self.run_cli(
            ["ask", "ready?", "--context", "x", "--ref", "task:demo/T01"], "sess-1", self.repo_dir
        )
        code, out, err = self.run_cli(["answer", "1", "x" * 1001], None, None)
        self.assertEqual(code, 1)
        self.assertIn("exceeds the maximum length", err)

    def test_answer_rejects_email(self):
        self.run_cli(
            ["ask", "ready?", "--context", "x", "--ref", "task:demo/T01"], "sess-1", self.repo_dir
        )
        code, out, err = self.run_cli(["answer", "1", "ping jane.doe@example.com"], None, None)
        self.assertEqual(code, 1)
        self.assertIn("must not contain an email address", err)


if __name__ == "__main__":
    import unittest

    unittest.main()
