from tests.testutil import GuildTestCase


class SyncTests(GuildTestCase):
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

    def test_sync_flips_merged_pr(self):
        self.write_gh_fixture(
            "view_acme-app_1",
            {
                "state": "MERGED", "isDraft": False, "headRefName": "feature/x", "title": "t",
                "mergedAt": "2026-01-01T00:00:00Z",
                "statusCheckRollup": [{"conclusion": "SUCCESS"}, {"conclusion": "FAILURE"}],
            },
        )
        code, out, err = self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0)
        code, out, err = self.run_cli(["board"], "sess-1", self.repo_dir)
        self.assertIn("app#1  merged  ✗1 ✓1", out)

    def test_sync_closes_notice_when_until_met(self):
        self.run_cli(
            [
                "notice", "create", "waiting on merge", "--to", "guild", "--ttl", "8h",
                "--until", "pr:acme/app#1:merged",
            ],
            None, None,
        )
        self.write_gh_fixture(
            "view_acme-app_1",
            {
                "state": "MERGED", "isDraft": False, "headRefName": "feature/x", "title": "t",
                "mergedAt": "2026-01-01T00:00:00Z", "statusCheckRollup": [],
            },
        )
        self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["notices"], None, None)
        self.assertEqual(out, "")

    def test_sync_reports_gh_failure_and_continues(self):
        self.write_gh_error("view_acme-app_1", "rate limited")
        code, out, err = self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)
        self.assertEqual(code, 1)
        self.assertIn("sync failed for acme/app#1", err)

    def test_unimplemented_source_rejected(self):
        code, out, err = self.run_cli(["sync", "--source", "jira"], "sess-1", self.repo_dir)
        self.assertEqual(code, 1)
        self.assertIn("not implemented", err)


if __name__ == "__main__":
    import unittest

    unittest.main()
