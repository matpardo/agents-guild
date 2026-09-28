from tests.testutil import GuildTestCase


class QuestAddValidationTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha"], "sess-1", self.repo_dir)

    def test_quest_add_without_project_fails(self):
        code, out, err = self.run_cli(
            ["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", self.root
        )
        self.assertEqual(code, 1)
        self.assertIn("no project config matches", err)

    def test_epic_quest_requires_synced_epic(self):
        code, out, err = self.run_cli(
            [
                "quest", "add", "demo", "--title", "Demo", "--epic", "compliance",
                "--tasks", "T01,T02",
            ],
            "sess-1",
            self.repo_dir,
        )
        self.assertEqual(code, 1)
        self.assertIn("never synced", err)
        self.assertIn("guild sync --source sdd", err)

    def test_epic_quest_requires_tasks(self):
        code, out, err = self.run_cli(
            ["quest", "add", "demo", "--title", "Demo", "--epic", "compliance"], "sess-1", self.repo_dir
        )
        self.assertEqual(code, 1)
        self.assertIn("--epic and --tasks", err)

    def test_no_epic_cannot_combine_with_epic(self):
        code, out, err = self.run_cli(
            ["quest", "add", "demo", "--title", "Demo", "--no-epic", "--epic", "x"],
            "sess-1",
            self.repo_dir,
        )
        self.assertEqual(code, 1)

    def test_epic_quest_created_with_queued_tasks(self):
        self.sync_sdd(
            self.repo_dir,
            "sess-1",
            "acme",
            "compliance",
            "## T01 — First task\n\n**Deps:** —\n\n**Status:** [ ] pending\n\n"
            "## T02 — Second task\n\n**Deps:** —\n\n**Status:** [ ] pending\n",
        )
        code, out, err = self.run_cli(
            [
                "quest",
                "add",
                "demo",
                "--title",
                "Demo",
                "--epic",
                "compliance",
                "--tasks",
                "T01,T02",
            ],
            "sess-1",
            self.repo_dir,
        )
        self.assertEqual(code, 0)
        code, out, err = self.run_cli(["board"], "sess-1", self.repo_dir)
        self.assertIn("queued: T01, T02", out)

    def test_epic_quest_rejects_unknown_tid(self):
        self.sync_sdd(
            self.repo_dir,
            "sess-1",
            "acme",
            "compliance",
            "## T01 — First task\n\n**Deps:** —\n\n**Status:** [ ] pending\n",
        )
        code, out, err = self.run_cli(
            [
                "quest", "add", "demo", "--title", "Demo", "--epic", "compliance",
                "--tasks", "T01,T99",
            ],
            "sess-1",
            self.repo_dir,
        )
        self.assertEqual(code, 1)
        self.assertIn("T99", err)
        self.assertIn("not found in epic", err)

    def test_epic_quest_copies_real_titles(self):
        self.sync_sdd(
            self.repo_dir,
            "sess-1",
            "acme",
            "compliance",
            "## T01 — Configure retries\n\n**Deps:** —\n\n**Status:** [ ] pending\n",
        )
        self.run_cli(
            ["quest", "add", "demo", "--title", "Demo", "--epic", "compliance", "--tasks", "T01"],
            "sess-1",
            self.repo_dir,
        )
        self.run_cli(["task", "start", "demo/T01"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["board"], "sess-1", self.repo_dir)
        self.assertIn("Configure retries", out)

    def test_no_epic_quest_created_without_tasks(self):
        code, out, err = self.run_cli(
            ["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", self.repo_dir
        )
        self.assertEqual(code, 0)

    def test_duplicate_slug_rejected(self):
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(
            ["quest", "add", "demo", "--title", "Demo again", "--no-epic"], "sess-1", self.repo_dir
        )
        self.assertEqual(code, 1)
        self.assertIn("already exists", err)


class TaskLifecycleTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha"], "sess-1", self.repo_dir)
        self.run_cli(
            ["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", self.repo_dir
        )

    def test_add_task_to_no_epic_quest(self):
        code, out, err = self.run_cli(
            ["task", "add", "demo/T01", "--title", "First task"], "sess-1", self.repo_dir
        )
        self.assertEqual(code, 0)

    def test_cannot_add_task_to_epic_quest(self):
        self.sync_sdd(
            self.repo_dir,
            "sess-1",
            "acme",
            "compliance",
            "## T09 — Ninth task\n\n**Deps:** —\n\n**Status:** [ ] pending\n",
        )
        self.run_cli(
            ["quest", "add", "epicq", "--title", "E", "--epic", "compliance", "--tasks", "T09"],
            "sess-1",
            self.repo_dir,
        )
        code, out, err = self.run_cli(
            ["task", "add", "epicq/T10", "--title", "Extra"], "sess-1", self.repo_dir
        )
        self.assertEqual(code, 1)
        self.assertIn("epic quest", err)

    def test_start_block_done_cycle(self):
        self.run_cli(["task", "add", "demo/T01", "--title", "First"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(
            ["task", "start", "demo/T01", "--summary", "wip"], "sess-1", self.repo_dir
        )
        self.assertEqual(code, 0)
        code, out, err = self.run_cli(
            ["task", "block", "demo/T01", "--reason", "waiting on ci"], "sess-1", self.repo_dir
        )
        self.assertEqual(code, 0)
        code, out, err = self.run_cli(["board"], "sess-1", self.repo_dir)
        self.assertIn("blocked: T01 — waiting on ci", out)
        code, out, err = self.run_cli(
            ["task", "done", "demo/T01", "--summary", "shipped"], "sess-1", self.repo_dir
        )
        self.assertEqual(code, 0)

    def test_block_requires_reason(self):
        self.run_cli(["task", "add", "demo/T01", "--title", "First"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["task", "block", "demo/T01"], "sess-1", self.repo_dir)
        self.assertEqual(code, 2)

    def test_done_task_cannot_transition_again(self):
        self.run_cli(["task", "add", "demo/T01", "--title", "First"], "sess-1", self.repo_dir)
        self.run_cli(["task", "done", "demo/T01"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["task", "start", "demo/T01"], "sess-1", self.repo_dir)
        self.assertEqual(code, 1)
        self.assertIn("already done", err)

    def test_other_party_cannot_mutate_task(self):
        self.run_cli(["task", "add", "demo/T01", "--title", "First"], "sess-1", self.repo_dir)
        self.run_cli(["party", "start", "beta"], "sess-2", self.repo_dir)
        code, out, err = self.run_cli(["task", "start", "demo/T01"], "sess-2", self.repo_dir)
        self.assertEqual(code, 1)
        self.assertIn("owned by party", err)


if __name__ == "__main__":
    import unittest

    unittest.main()
