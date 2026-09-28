import sqlite3

from tests.testutil import GuildTestCase


class PrActivityTests(GuildTestCase):
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

    def _pr_row(self):
        conn = sqlite3.connect(str(self.data_home / "guild" / "guild.db"))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM prs WHERE repo = 'acme/app' AND number = 1").fetchone()
        conn.close()
        return row

    def test_track_initializes_activity_columns(self):
        row = self._pr_row()
        self.assertIsNone(row["mergeable"])
        self.assertEqual(row["review_comment_count"], 0)
        self.assertEqual(row["last_notified_comment_count"], 0)
        self.assertIsNotNone(row["last_activity_at"])

    def test_sync_populates_mergeable_and_review_comment_count(self):
        self.write_gh_fixture(
            "view_acme-app_1",
            {
                "state": "OPEN", "isDraft": True, "headRefName": "feature/x", "title": "t",
                "mergeable": "CONFLICTING",
                "comments": [{"id": 1}, {"id": 2}],
                "reviews": [{"id": 3}],
            },
        )
        code, out, err = self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0)
        row = self._pr_row()
        self.assertEqual(row["mergeable"], "CONFLICTING")
        self.assertEqual(row["review_comment_count"], 3)
        self.assertEqual(row["last_notified_comment_count"], 0)

    def test_sync_without_changes_does_not_bump_activity(self):
        self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)
        before = self._pr_row()["last_activity_at"]
        self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)
        after = self._pr_row()["last_activity_at"]
        self.assertEqual(before, after)

    def test_sync_with_new_comments_bumps_activity(self):
        self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)
        before = self._pr_row()["last_activity_at"]
        self.write_gh_fixture(
            "view_acme-app_1",
            {
                "state": "OPEN", "isDraft": True, "headRefName": "feature/x", "title": "t",
                "comments": [{"id": 1}],
            },
        )
        self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)
        after = self._pr_row()["last_activity_at"]
        self.assertNotEqual(before, after)

    def test_pr_set_bumps_activity_when_lifecycle_changes(self):
        before = self._pr_row()["last_activity_at"]
        self.run_cli(["pr", "set", "acme/app#1", "--lifecycle", "ready"], "sess-1", self.repo_dir)
        after = self._pr_row()["last_activity_at"]
        self.assertNotEqual(before, after)

    def test_pr_set_does_not_bump_activity_when_nothing_changes(self):
        self.run_cli(["pr", "set", "acme/app#1", "--waits", "y"], "sess-1", self.repo_dir)
        before = self._pr_row()["last_activity_at"]
        self.run_cli(["pr", "set", "acme/app#1", "--waits", "y"], "sess-1", self.repo_dir)
        after = self._pr_row()["last_activity_at"]
        self.assertEqual(before, after)


if __name__ == "__main__":
    import unittest

    unittest.main()
