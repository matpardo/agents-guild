from tests.testutil import GuildTestCase


class PrTrackTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha"], "sess-1", self.repo_dir)
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", self.repo_dir)
        self.run_cli(["task", "add", "demo/T01", "--title", "First"], "sess-1", self.repo_dir)

    def test_track_rejects_repo_outside_project_config(self):
        code, out, err = self.run_cli(
            [
                "pr", "track", "other/repo#1", "--task", "demo/T01",
                "--what", "x", "--waits", "y",
            ],
            "sess-1", self.repo_dir,
        )
        self.assertEqual(code, 1)
        self.assertIn("not in project", err)

    def test_track_rejects_unknown_task(self):
        code, out, err = self.run_cli(
            [
                "pr", "track", "acme/app#1", "--task", "demo/T99",
                "--what", "x", "--waits", "y",
            ],
            "sess-1", self.repo_dir,
        )
        self.assertEqual(code, 1)
        self.assertIn("unknown task", err)

    def test_track_calls_gh_and_stores_result(self):
        self.write_gh_fixture(
            "view_acme-app_1",
            {"state": "OPEN", "isDraft": True, "headRefName": "feature/x", "title": "demo title"},
        )
        code, out, err = self.run_cli(
            [
                "pr", "track", "acme/app#1", "--task", "demo/T01",
                "--what", "adds flag", "--waits", "review",
            ],
            "sess-1", self.repo_dir,
        )
        self.assertEqual(code, 0)
        code, out, err = self.run_cli(["board"], "sess-1", self.repo_dir)
        self.assertIn("acme/app#1 [draft]", out)
        self.assertIn("waits: review", out)

    def test_track_rejects_duplicate(self):
        self.write_gh_fixture(
            "view_acme-app_1",
            {"state": "OPEN", "isDraft": True, "headRefName": "feature/x", "title": "t"},
        )
        self.run_cli(
            ["pr", "track", "acme/app#1", "--task", "demo/T01", "--what", "x", "--waits", "y"],
            "sess-1", self.repo_dir,
        )
        code, out, err = self.run_cli(
            ["pr", "track", "acme/app#1", "--task", "demo/T01", "--what", "x", "--waits", "y"],
            "sess-1", self.repo_dir,
        )
        self.assertEqual(code, 1)
        self.assertIn("already tracked", err)

    def test_track_reports_gh_failure(self):
        self.write_gh_error("view_acme-app_1", "not found")
        code, out, err = self.run_cli(
            ["pr", "track", "acme/app#1", "--task", "demo/T01", "--what", "x", "--waits", "y"],
            "sess-1", self.repo_dir,
        )
        self.assertEqual(code, 1)
        self.assertIn("gh pr view failed", err)


class PrSetTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha"], "sess-1", self.repo_dir)
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", self.repo_dir)
        self.run_cli(["task", "add", "demo/T01", "--title", "First"], "sess-1", self.repo_dir)
        self.write_gh_fixture(
            "view_acme-app_1",
            {"state": "OPEN", "isDraft": True, "headRefName": "feature/x", "title": "t"},
        )
        self.run_cli(
            ["pr", "track", "acme/app#1", "--task", "demo/T01", "--what", "x", "--waits", "y"],
            "sess-1", self.repo_dir,
        )

    def test_set_requires_lifecycle_or_waits(self):
        code, out, err = self.run_cli(["pr", "set", "acme/app#1"], "sess-1", self.repo_dir)
        self.assertEqual(code, 1)
        self.assertIn("--lifecycle and/or --waits", err)

    def test_set_updates_lifecycle(self):
        code, out, err = self.run_cli(
            ["pr", "set", "acme/app#1", "--lifecycle", "ready"], "sess-1", self.repo_dir
        )
        self.assertEqual(code, 0)
        code, out, err = self.run_cli(["board"], "sess-1", self.repo_dir)
        self.assertIn("[ready]", out)

    def test_set_unknown_pr_fails(self):
        code, out, err = self.run_cli(
            ["pr", "set", "acme/app#99", "--lifecycle", "ready"], "sess-1", self.repo_dir
        )
        self.assertEqual(code, 1)
        self.assertIn("is not tracked", err)


if __name__ == "__main__":
    import unittest

    unittest.main()
