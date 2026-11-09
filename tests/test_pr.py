import sqlite3

from tests.testutil import GuildTestCase


class PrTrackTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(
            ["party", "start", "alpha", "--reason", "test reason", "--goal", "test goal", "--done-when", "test done"],
            "sess-1",
            self.repo_dir,
        )
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", self.repo_dir)
        self.run_cli(
            ["task", "add", "demo/T01", "--title", "First", "--reason", "serves the goal"], "sess-1", self.repo_dir
        )

    def test_track_rejects_repo_outside_project_config(self):
        code, out, err = self.run_cli(
            [
                "pr",
                "track",
                "other/repo#1",
                "--task",
                "demo/T01",
                "--what",
                "x",
                "--waits",
                "y",
            ],
            "sess-1",
            self.repo_dir,
        )
        self.assertEqual(code, 1)
        self.assertIn("not in project", err)

    def test_track_rejects_unknown_task(self):
        code, out, err = self.run_cli(
            [
                "pr",
                "track",
                "acme/app#1",
                "--task",
                "demo/T99",
                "--what",
                "x",
                "--waits",
                "y",
            ],
            "sess-1",
            self.repo_dir,
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
                "pr",
                "track",
                "acme/app#1",
                "--task",
                "demo/T01",
                "--what",
                "adds flag",
                "--waits",
                "review",
            ],
            "sess-1",
            self.repo_dir,
        )
        self.assertEqual(code, 0)
        code, out, err = self.run_cli(["board"], "sess-1", self.repo_dir)
        self.assertIn("app#1  draft", out)
        self.assertIn("waits: review", out)

    def _track_row(self, extra):
        self.write_gh_fixture(
            "view_acme-app_1",
            {"state": "OPEN", "isDraft": True, "headRefName": "feature/x", "title": "t"},
        )
        code, out, err = self.run_cli(
            ["pr", "track", "acme/app#1", "--task", "demo/T01", "--what", "x", "--waits", "y"] + extra,
            "sess-1",
            self.repo_dir,
        )
        self.assertEqual(code, 0, err)
        conn = sqlite3.connect(str(self.data_home / "guild" / "guild.db"))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT needs_ask_answer, needs_human_pr_review, fixes_main, fixes_flaky FROM prs"
        ).fetchone()
        conn.close()
        return row

    def _track_flags(self, extra):
        row = self._track_row(extra)
        return row["needs_ask_answer"], row["needs_human_pr_review"]

    def _track_marks(self, extra):
        row = self._track_row(extra)
        return row["fixes_main"], row["fixes_flaky"]

    def test_track_without_the_review_flag_starts_with_both_flags_off(self):
        self.assertEqual(self._track_flags([]), (0, 0))

    def test_track_with_the_review_flag_sets_it(self):
        self.assertEqual(self._track_flags(["--needs-human-pr-review"]), (0, 1))

    def test_track_without_mark_options_starts_with_both_marks_off(self):
        self.assertEqual(self._track_marks([]), (0, 0))

    def test_track_sets_the_main_mark(self):
        self.assertEqual(self._track_marks(["--fixes-main"]), (1, 0))

    def test_track_sets_the_flaky_mark(self):
        self.assertEqual(self._track_marks(["--fixes-flaky"]), (0, 1))

    def test_track_sets_both_marks(self):
        self.assertEqual(self._track_marks(["--fixes-main", "--fixes-flaky"]), (1, 1))

    def test_track_rejects_the_removed_type_option(self):
        code, out, err = self.run_cli(
            [
                "pr",
                "track",
                "acme/app#1",
                "--task",
                "demo/T01",
                "--what",
                "x",
                "--waits",
                "y",
                "--type",
                "hotfix",
            ],
            "sess-1",
            self.repo_dir,
        )
        self.assertEqual(code, 2)
        self.assertIn("--type", err)

    def test_board_shows_the_full_branch_under_the_pr(self):
        self._track_row([])
        code, out, err = self.run_cli(["board"], "sess-1", self.repo_dir)
        self.assertIn("branch: feature/x", out)

    def test_board_shows_no_type_badge(self):
        self._track_row([])
        code, out, err = self.run_cli(["board"], "sess-1", self.repo_dir)
        self.assertIn("app#1  draft  ", out)

    def test_board_shows_the_marks_as_badges(self):
        self._track_row(["--fixes-main", "--fixes-flaky"])
        code, out, err = self.run_cli(["board"], "sess-1", self.repo_dir)
        self.assertIn("app#1  draft fixes-main fixes-flaky", out)

    def test_track_rejects_duplicate(self):
        self.write_gh_fixture(
            "view_acme-app_1",
            {"state": "OPEN", "isDraft": True, "headRefName": "feature/x", "title": "t"},
        )
        self.run_cli(
            ["pr", "track", "acme/app#1", "--task", "demo/T01", "--what", "x", "--waits", "y"],
            "sess-1",
            self.repo_dir,
        )
        code, out, err = self.run_cli(
            ["pr", "track", "acme/app#1", "--task", "demo/T01", "--what", "x", "--waits", "y"],
            "sess-1",
            self.repo_dir,
        )
        self.assertEqual(code, 1)
        self.assertIn("already tracked", err)

    def test_track_reports_gh_failure(self):
        self.write_gh_error("view_acme-app_1", "not found")
        code, out, err = self.run_cli(
            ["pr", "track", "acme/app#1", "--task", "demo/T01", "--what", "x", "--waits", "y"],
            "sess-1",
            self.repo_dir,
        )
        self.assertEqual(code, 1)
        self.assertIn("gh pr view failed", err)


class PrTrackCardTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.write_gh_fixture(
            "view_acme-app_1",
            {"state": "OPEN", "isDraft": True, "headRefName": "feature/x", "title": "t"},
        )

    def _track(self, session_id, extra):
        return self.run_cli(
            ["pr", "track", "acme/app#1", "--what", "x", "--waits", "y"] + extra,
            session_id,
            self.repo_dir,
        )

    def _start_party_with_task(self):
        self.run_cli(
            ["party", "start", "alpha", "--reason", "test reason", "--goal", "test goal", "--done-when", "test done"],
            "sess-1",
            self.repo_dir,
        )
        self.run_cli(
            ["quest", "add", "demo", "--title", "Demo", "--no-epic", "--tasks", "T01"], "sess-1", self.repo_dir
        )

    def test_card_without_task_is_rejected_for_a_party(self):
        self._start_party_with_task()
        code, out, err = self._track("sess-1", ["--card", "ABC-123"])
        self.assertEqual(code, 1)
        self.assertIn("a party's PR belongs to one of its tasks", err)
        self.assertIn("guild task add", err)
        self.assertIn("guild quest add <slug> --no-epic", err)

    def test_neither_task_nor_card_is_rejected_for_a_party(self):
        self._start_party_with_task()
        code, out, err = self._track("sess-1", [])
        self.assertEqual(code, 1)
        self.assertIn("a party's PR belongs to one of its tasks", err)

    def test_task_together_with_card_stores_both(self):
        self._start_party_with_task()
        code, out, err = self._track("sess-1", ["--task", "demo/T01", "--card", "ABC-123"])
        self.assertEqual(code, 0, err)
        conn = sqlite3.connect(str(self.data_home / "guild" / "guild.db"))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT task_quest, task_tid, card, party FROM prs").fetchone()
        conn.close()
        self.assertEqual(
            (row["task_quest"], row["task_tid"], row["card"], row["party"]),
            ("demo", "T01", "ABC-123", "alpha"),
        )

    def test_unbound_session_is_rejected(self):
        code, out, err = self._track("sess-1", ["--card", "ABC-123"])
        self.assertEqual(code, 1)
        self.assertIn("session not bound", err)


class PrSetTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(
            ["party", "start", "alpha", "--reason", "test reason", "--goal", "test goal", "--done-when", "test done"],
            "sess-1",
            self.repo_dir,
        )
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", self.repo_dir)
        self.run_cli(
            ["task", "add", "demo/T01", "--title", "First", "--reason", "serves the goal"], "sess-1", self.repo_dir
        )
        self.write_gh_fixture(
            "view_acme-app_1",
            {"state": "OPEN", "isDraft": True, "headRefName": "feature/x", "title": "t"},
        )
        self.run_cli(
            ["pr", "track", "acme/app#1", "--task", "demo/T01", "--what", "x", "--waits", "y"],
            "sess-1",
            self.repo_dir,
        )

    def row(self):
        conn = sqlite3.connect(str(self.data_home / "guild" / "guild.db"))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT lifecycle, needs_ask_answer, needs_human_pr_review, fixes_main, fixes_flaky"
            " FROM prs WHERE number = 1"
        ).fetchone()
        conn.close()
        return row

    def flags(self):
        row = self.row()
        return row["lifecycle"], row["needs_ask_answer"], row["needs_human_pr_review"]

    def marks(self):
        row = self.row()
        return row["fixes_main"], row["fixes_flaky"]

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
            "sess-1",
            self.repo_dir,
        )
        self.assertNotEqual(code, 0)

    def test_set_rejects_the_old_needs_human_lifecycle(self):
        code, out, err = self.run_cli(
            ["pr", "set", "acme/app#1", "--lifecycle", "needs-human"], "sess-1", self.repo_dir
        )
        self.assertNotEqual(code, 0)
        self.assertIn("invalid choice", err)

    def test_set_updates_lifecycle(self):
        code, out, err = self.run_cli(["pr", "set", "acme/app#1", "--lifecycle", "ready"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0)
        code, out, err = self.run_cli(["board"], "sess-1", self.repo_dir)
        self.assertIn("app#1  ready", out)

    def test_set_toggles_the_main_mark(self):
        self.set_pr("--fixes-main")
        self.assertEqual(self.marks(), (1, 0))
        self.set_pr("--no-fixes-main")
        self.assertEqual(self.marks(), (0, 0))

    def test_set_toggles_the_flaky_mark(self):
        self.set_pr("--fixes-flaky")
        self.assertEqual(self.marks(), (0, 1))
        self.set_pr("--no-fixes-flaky")
        self.assertEqual(self.marks(), (0, 0))

    def test_set_without_a_mark_option_leaves_the_marks_unchanged(self):
        self.set_pr("--fixes-main", "--fixes-flaky")
        self.set_pr("--lifecycle", "converging")
        self.assertEqual(self.marks(), (1, 1))

    def test_set_rejects_the_removed_type_option(self):
        code, out, err = self.run_cli(["pr", "set", "acme/app#1", "--type", "docs"], "sess-1", self.repo_dir)
        self.assertEqual(code, 2)
        self.assertIn("--type", err)

    def test_set_unknown_pr_fails(self):
        code, out, err = self.run_cli(["pr", "set", "acme/app#99", "--lifecycle", "ready"], "sess-1", self.repo_dir)
        self.assertEqual(code, 1)
        self.assertIn("is not tracked", err)


if __name__ == "__main__":
    import unittest

    unittest.main()


class PrRelinkTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(
            ["party", "start", "alpha", "--reason", "test reason", "--goal", "test goal", "--done-when", "test done"],
            "sess-1",
            self.repo_dir,
        )
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", self.repo_dir)
        self.run_cli(
            ["task", "add", "demo/T01", "--title", "First", "--reason", "serves the goal"], "sess-1", self.repo_dir
        )
        self.run_cli(
            ["task", "add", "demo/T02", "--title", "Second", "--reason", "serves the goal"], "sess-1", self.repo_dir
        )
        self.write_gh_fixture(
            "view_acme-app_1",
            {"state": "OPEN", "isDraft": True, "headRefName": "feature/x", "title": "t"},
        )
        code, out, err = self.run_cli(
            ["pr", "track", "acme/app#1", "--task", "demo/T01", "--what", "x", "--waits", "y"],
            "sess-1",
            self.repo_dir,
        )
        self.assertEqual(code, 0, err)

    def _rows(self):
        conn = sqlite3.connect(str(self.data_home / "guild" / "guild.db"))
        conn.row_factory = sqlite3.Row
        try:
            return conn.execute("SELECT task_quest, task_tid, card, lifecycle FROM prs").fetchall()
        finally:
            conn.close()

    def test_set_task_relinks_the_pr(self):
        code, out, err = self.run_cli(["pr", "set", "acme/app#1", "--task", "demo/T02"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        row = self._rows()[0]
        self.assertEqual((row["task_quest"], row["task_tid"], row["lifecycle"]), ("demo", "T02", "draft"))

    def test_set_card_relinks_the_card_and_keeps_the_task(self):
        code, out, err = self.run_cli(["pr", "set", "acme/app#1", "--card", "DEMO-7"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        row = self._rows()[0]
        self.assertEqual((row["task_quest"], row["task_tid"], row["card"]), ("demo", "T01", "DEMO-7"))

    def test_set_unknown_task_is_refused(self):
        code, out, err = self.run_cli(["pr", "set", "acme/app#1", "--task", "demo/T99"], "sess-1", self.repo_dir)
        self.assertEqual(code, 1)
        self.assertIn("unknown task", err)

    def test_set_task_of_another_party_is_refused(self):
        self.write_session(2, "sess-2", "beta-session")
        self.run_cli(
            ["party", "start", "beta", "--reason", "test reason", "--goal", "test goal", "--done-when", "test done"],
            "sess-2",
            self.repo_dir,
        )
        self.run_cli(["quest", "add", "other", "--title", "Other", "--no-epic"], "sess-2", self.repo_dir)
        self.run_cli(
            ["task", "add", "other/T01", "--title", "Theirs", "--reason", "serves the goal"], "sess-2", self.repo_dir
        )
        code, out, err = self.run_cli(["pr", "set", "acme/app#1", "--task", "other/T01"], "sess-1", self.repo_dir)
        self.assertEqual(code, 1)
        self.assertIn("does not belong", err)

    def test_foreign_party_cannot_relink_or_untrack(self):
        self.write_session(2, "sess-2", "beta-session")
        self.run_cli(
            ["party", "start", "beta", "--reason", "test reason", "--goal", "test goal", "--done-when", "test done"],
            "sess-2",
            self.repo_dir,
        )
        code, out, err = self.run_cli(["pr", "set", "acme/app#1", "--card", "DEMO-7"], "sess-2", self.repo_dir)
        self.assertEqual(code, 1)
        self.assertIn("belongs to another session", err)
        code, out, err = self.run_cli(["pr", "untrack", "acme/app#1"], "sess-2", self.repo_dir)
        self.assertEqual(code, 1)
        self.assertEqual(len(self._rows()), 1)

    def test_untrack_removes_the_row_and_ready_check_says_not_tracked(self):
        code, out, err = self.run_cli(["pr", "untrack", "acme/app#1"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        self.assertEqual(self._rows(), [])
        code, out, err = self.run_cli(["pr", "ready-check", "acme/app#1"], "sess-1", self.repo_dir)
        self.assertEqual(code, 1)
        self.assertIn("not tracked", err)

    def test_untrack_unknown_pr_is_refused(self):
        code, out, err = self.run_cli(["pr", "untrack", "acme/app#9"], "sess-1", self.repo_dir)
        self.assertEqual(code, 1)
        self.assertIn("not tracked", err)

    def test_rebuild_replays_relink_and_untrack(self):
        self.run_cli(["pr", "set", "acme/app#1", "--task", "demo/T02"], "sess-1", self.repo_dir)
        self.run_cli(["rebuild"], None, None)
        self.assertEqual(self._rows()[0]["task_tid"], "T02")
        self.run_cli(["pr", "untrack", "acme/app#1"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["rebuild"], None, None)
        self.assertEqual(code, 0, err)
        self.assertEqual(self._rows(), [])
