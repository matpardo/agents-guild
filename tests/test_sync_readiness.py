from tests.testutil import GuildTestCase


class SyncReadinessTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha"], "sess-1", self.repo_dir)
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", self.repo_dir)
        self.run_cli(["task", "add", "demo/T01", "--title", "First"], "sess-1", self.repo_dir)
        self.write_view({"state": "OPEN", "isDraft": True})
        self.run_cli(
            ["pr", "track", "acme/app#1", "--task", "demo/T01", "--what", "x", "--waits", "y"],
            "sess-1", self.repo_dir,
        )

    def write_view(self, fields):
        view = {"headRefName": "feature/x", "title": "t", "statusCheckRollup": [], "mergeable": "MERGEABLE"}
        view.update(fields)
        self.write_gh_fixture("view_acme-app_1", view)

    def set_lifecycle(self, lifecycle):
        code, out, err = self.run_cli(
            ["pr", "set", "acme/app#1", "--lifecycle", lifecycle], "sess-1", self.repo_dir
        )
        self.assertEqual(code, 0, err)
        return out

    def sync_board(self, fields):
        self.write_view(fields)
        code, out, err = self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        code, out, err = self.run_cli(["board"], "sess-1", self.repo_dir)
        return out

    def test_non_draft_open_pr_enters_merge_queue_after_sync(self):
        self.sync_board({"state": "OPEN", "isDraft": False})
        code, out, err = self.run_cli(["merge-queue", "--party", "alpha"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        self.assertNotIn("blocked", out)
        self.assertIn("app#1", out)

    def test_non_draft_open_pr_becomes_ready_from_every_lifecycle(self):
        for lifecycle in ("draft", "converging", "ready"):
            self.set_lifecycle(lifecycle)
            board = self.sync_board({"state": "OPEN", "isDraft": False})
            self.assertIn("app#1  ready", board, lifecycle)

    def test_draft_pr_keeps_converging(self):
        self.set_lifecycle("converging")
        board = self.sync_board({"state": "OPEN", "isDraft": True})
        self.assertIn("app#1  converging", board)

    def test_sync_keeps_both_flags_when_pr_goes_ready_on_github(self):
        code, out, err = self.run_cli(
            ["pr", "set", "acme/app#1", "--needs-ask-answer", "--needs-human-pr-review"],
            "sess-1", self.repo_dir,
        )
        self.assertEqual(code, 0, err)
        board = self.sync_board({"state": "OPEN", "isDraft": False})
        self.assertIn("app#1  ready needs-ask-answer needs-human-pr-review", board)

    def test_draft_pr_demotes_stale_ready_to_draft(self):
        self.set_lifecycle("ready")
        board = self.sync_board({"state": "OPEN", "isDraft": True})
        self.assertIn("app#1  draft", board)

    def test_draft_pr_stays_draft(self):
        board = self.sync_board({"state": "OPEN", "isDraft": True})
        self.assertIn("app#1  draft", board)

    def test_missing_is_draft_keeps_current_lifecycle(self):
        self.set_lifecycle("converging")
        board = self.sync_board({"state": "OPEN"})
        self.assertIn("app#1  converging", board)

    def test_merged_wins_over_non_draft(self):
        board = self.sync_board({"state": "MERGED", "isDraft": False, "mergedAt": "2026-01-01T00:00:00Z"})
        self.assertIn("app#1  merged", board)

    def test_closed_wins_over_non_draft(self):
        board = self.sync_board({"state": "CLOSED", "isDraft": False})
        self.assertIn("app#1  closed", board)

    def test_set_ready_hints_when_pr_is_draft_on_github(self):
        out = self.set_lifecycle("ready")
        self.assertIn(
            "PR is draft on GitHub; mark it ready there (gh pr ready 1) or the next sync reverts it", out
        )

    def test_set_ready_no_hint_when_pr_is_not_draft_on_github(self):
        self.sync_board({"state": "OPEN", "isDraft": False})
        out = self.set_lifecycle("ready")
        self.assertNotIn("draft on GitHub", out)

    def test_set_converging_no_hint_when_pr_is_draft_on_github(self):
        out = self.set_lifecycle("converging")
        self.assertNotIn("draft on GitHub", out)


if __name__ == "__main__":
    import unittest

    unittest.main()
