import sqlite3

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
        self.assertIn("app#1  draft", out)
        self.assertIn("waits: review", out)

    def _track_flags(self, extra):
        self.write_gh_fixture(
            "view_acme-app_1",
            {"state": "OPEN", "isDraft": True, "headRefName": "feature/x", "title": "t"},
        )
        code, out, err = self.run_cli(
            ["pr", "track", "acme/app#1", "--task", "demo/T01", "--what", "x", "--waits", "y"] + extra,
            "sess-1", self.repo_dir,
        )
        self.assertEqual(code, 0, err)
        conn = sqlite3.connect(str(self.data_home / "guild" / "guild.db"))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT needs_ask_answer, needs_human_pr_review FROM prs").fetchone()
        conn.close()
        return row["needs_ask_answer"], row["needs_human_pr_review"]

    def test_track_without_the_review_flag_starts_with_both_flags_off(self):
        self.assertEqual(self._track_flags([]), (0, 0))

    def test_track_with_the_review_flag_sets_it(self):
        self.assertEqual(self._track_flags(["--needs-human-pr-review"]), (0, 1))

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

    def flags(self):
        conn = sqlite3.connect(str(self.data_home / "guild" / "guild.db"))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT lifecycle, needs_ask_answer, needs_human_pr_review FROM prs WHERE number = 1"
        ).fetchone()
        conn.close()
        return row["lifecycle"], row["needs_ask_answer"], row["needs_human_pr_review"]

    def set_pr(self, *options):
        code, out, err = self.run_cli(["pr", "set", "acme/app#1"] + list(options), "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)

    def test_set_requires_at_least_one_option(self):
        code, out, err = self.run_cli(["pr", "set", "acme/app#1"], "sess-1", self.repo_dir)
        self.assertEqual(code, 1)
        self.assertIn("pr set needs at least one of", err)
        self.assertIn("--needs-ask-answer/--no-needs-ask-answer", err)

    def test_new_pr_has_both_flags_off(self):
        self.assertEqual(self.flags(), ("draft", 0, 0))

    def test_set_toggles_needs_ask_answer(self):
        self.set_pr("--needs-ask-answer")
        self.assertEqual(self.flags(), ("draft", 1, 0))
        self.set_pr("--no-needs-ask-answer")
        self.assertEqual(self.flags(), ("draft", 0, 0))

    def test_set_toggles_needs_human_pr_review(self):
        self.set_pr("--needs-human-pr-review")
        self.assertEqual(self.flags(), ("draft", 0, 1))
        self.set_pr("--no-needs-human-pr-review")
        self.assertEqual(self.flags(), ("draft", 0, 0))

    def test_set_without_a_flag_option_leaves_flags_unchanged(self):
        self.set_pr("--needs-ask-answer", "--needs-human-pr-review")
        self.set_pr("--lifecycle", "converging")
        self.assertEqual(self.flags(), ("converging", 1, 1))

    def test_set_rejects_both_polarities_of_one_flag(self):
        code, out, err = self.run_cli(
            ["pr", "set", "acme/app#1", "--needs-ask-answer", "--no-needs-ask-answer"],
            "sess-1", self.repo_dir,
        )
        self.assertNotEqual(code, 0)

    def test_set_rejects_the_old_needs_human_lifecycle(self):
        code, out, err = self.run_cli(
            ["pr", "set", "acme/app#1", "--lifecycle", "needs-human"], "sess-1", self.repo_dir
        )
        self.assertNotEqual(code, 0)
        self.assertIn("invalid choice", err)

    def test_set_updates_lifecycle(self):
        code, out, err = self.run_cli(
            ["pr", "set", "acme/app#1", "--lifecycle", "ready"], "sess-1", self.repo_dir
        )
        self.assertEqual(code, 0)
        code, out, err = self.run_cli(["board"], "sess-1", self.repo_dir)
        self.assertIn("app#1  ready", out)

    def test_set_unknown_pr_fails(self):
        code, out, err = self.run_cli(
            ["pr", "set", "acme/app#99", "--lifecycle", "ready"], "sess-1", self.repo_dir
        )
        self.assertEqual(code, 1)
        self.assertIn("is not tracked", err)


if __name__ == "__main__":
    import unittest

    unittest.main()
