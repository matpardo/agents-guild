import sqlite3

from guild import db, origin, paths, reducers, timeutil
from guild.commands import pr as pr_commands
from guild.context import RunContext
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

    def _sync_view(self, **fields):
        view = {"state": "OPEN", "isDraft": False, "headRefName": "feature/x", "title": "t"}
        self.write_gh_fixture("view_acme-app_1", dict(view, **fields))
        code, out, err = self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0)
        return self._pr_row()

    def test_sync_stores_review_decision_merge_state_and_base_branch(self):
        row = self._sync_view(reviewDecision="APPROVED", mergeStateStatus="BLOCKED", baseRefName="main")
        self.assertEqual(
            (row["review_decision"], row["merge_state"], row["base_branch"]), ("APPROVED", "BLOCKED", "main")
        )

    def test_unknown_merge_state_keeps_the_previous_value(self):
        self._sync_view(mergeStateStatus="CLEAN", baseRefName="main")
        row = self._sync_view(mergeStateStatus="UNKNOWN", baseRefName="main")
        self.assertEqual(row["merge_state"], "CLEAN")

    def test_replaying_an_old_pr_synced_event_leaves_the_new_fields_empty(self):
        self._sync_view(reviewDecision="APPROVED", mergeStateStatus="CLEAN", baseRefName="main")
        conn = db.connect(paths.db_path())
        conn.execute(
            "UPDATE events SET payload = json_remove(payload, '$.review_decision', '$.merge_state', '$.base_branch')"
            " WHERE kind = 'pr.synced'"
        )
        conn.commit()
        conn.close()
        code, out, err = self.run_cli(["rebuild"], None, None)
        self.assertEqual(code, 0)
        row = self._pr_row()
        self.assertEqual((row["review_decision"], row["merge_state"], row["base_branch"]), (None, None, None))

    def _write_threads(self, resolved_flags):
        nodes = [{"isResolved": flag} for flag in resolved_flags]
        self.write_gh_fixture(
            "threads_acme-app_1",
            {"data": {"repository": {"pullRequest": {"reviewThreads": {"nodes": nodes}}}}},
        )

    def test_sync_stores_unresolved_thread_count_ignoring_resolved_threads(self):
        self._write_threads([False, True, False])
        row = self._sync_view()
        self.assertEqual(row["unresolved_threads"], 2)

    def test_threads_error_keeps_the_old_value_and_reports_failure(self):
        self._write_threads([False])
        self._sync_view()
        (self.gh_fixtures_dir / "threads_acme-app_1.json").unlink()
        self.write_gh_error("threads_acme-app_1", "graphql down")
        self.write_gh_fixture(
            "view_acme-app_1", {"state": "OPEN", "isDraft": False, "headRefName": "feature/x", "title": "t"}
        )
        code, out, err = self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)
        self.assertIn("review threads check failed: graphql down", out + err)
        self.assertEqual(self._pr_row()["unresolved_threads"], 1)

    def test_merged_pr_does_not_query_threads(self):
        self.write_gh_error("threads_acme-app_1", "must not be called")
        row = self._sync_view(state="MERGED", mergedAt="2026-01-01T00:00:00Z")
        self.assertEqual(row["lifecycle"], "merged")
        self.assertIsNone(row["unresolved_threads"])

    def test_replaying_an_old_pr_synced_event_leaves_unresolved_threads_empty(self):
        self._write_threads([False])
        self._sync_view()
        conn = db.connect(paths.db_path())
        conn.execute("UPDATE events SET payload = json_remove(payload, '$.unresolved_threads') WHERE kind = 'pr.synced'")
        conn.commit()
        conn.close()
        code, out, err = self.run_cli(["rebuild"], None, None)
        self.assertEqual(code, 0)
        self.assertIsNone(self._pr_row()["unresolved_threads"])

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

    def test_pr_set_bumps_activity_when_a_flag_changes(self):
        before = self._pr_row()["last_activity_at"]
        self.run_cli(["pr", "set", "acme/app#1", "--needs-human-pr-review"], "sess-1", self.repo_dir)
        after = self._pr_row()["last_activity_at"]
        self.assertNotEqual(before, after)

    def test_pr_set_does_not_bump_activity_when_a_flag_is_set_to_its_current_value(self):
        self.run_cli(["pr", "set", "acme/app#1", "--needs-ask-answer"], "sess-1", self.repo_dir)
        before = self._pr_row()["last_activity_at"]
        self.run_cli(["pr", "set", "acme/app#1", "--needs-ask-answer"], "sess-1", self.repo_dir)
        after = self._pr_row()["last_activity_at"]
        self.assertEqual(before, after)

    def test_pr_set_does_not_bump_activity_when_nothing_changes(self):
        self.run_cli(["pr", "set", "acme/app#1", "--waits", "y"], "sess-1", self.repo_dir)
        before = self._pr_row()["last_activity_at"]
        self.run_cli(["pr", "set", "acme/app#1", "--waits", "y"], "sess-1", self.repo_dir)
        after = self._pr_row()["last_activity_at"]
        self.assertEqual(before, after)

    def test_pr_synced_reducer_tolerates_legacy_payload_missing_new_fields(self):
        conn = db.connect(paths.db_path())
        legacy_event = {
            "ts": timeutil.to_iso(timeutil.utcnow()),
            "payload": {
                "repo": "acme/app",
                "number": 1,
                "gh_state": "OPEN",
                "gh_draft": False,
                "branch": "feature/x",
                "title": "t",
                "checks_failing": 0,
                "checks_passing": 0,
                "lifecycle": "ready",
                "synced_at": timeutil.to_iso(timeutil.utcnow()),
            },
        }
        reducers.apply(conn, dict(legacy_event, kind="pr.synced"))
        row = conn.execute("SELECT * FROM prs WHERE repo = 'acme/app' AND number = 1").fetchone()
        self.assertEqual(row["lifecycle"], "ready")
        self.assertIsNone(row["mergeable"])
        self.assertEqual(row["review_comment_count"], 0)
        conn.close()

    def _apply_pr_set(self, payload):
        conn = db.connect(paths.db_path())
        event = {
            "ts": timeutil.to_iso(timeutil.utcnow()),
            "kind": "pr.set",
            "payload": dict({"repo": "acme/app", "number": 1, "waits": "y"}, **payload),
        }
        reducers.apply(conn, event)
        conn.close()
        return self._pr_row()

    def test_legacy_pr_set_needs_human_replays_as_draft_with_the_ask_flag(self):
        row = self._apply_pr_set({"lifecycle": "needs-human"})
        self.assertEqual(
            (row["lifecycle"], row["needs_ask_answer"], row["needs_human_pr_review"]), ("draft", 1, 0)
        )

    def test_legacy_pr_set_without_flag_keys_carries_flags_forward(self):
        self.run_cli(["pr", "set", "acme/app#1", "--needs-human-pr-review"], "sess-1", self.repo_dir)
        row = self._apply_pr_set({"lifecycle": "converging"})
        self.assertEqual(
            (row["lifecycle"], row["needs_ask_answer"], row["needs_human_pr_review"]), ("converging", 0, 1)
        )

    def test_legacy_pr_tracked_without_flag_keys_inits_flags_to_zero(self):
        conn = db.connect(paths.db_path())
        reducers.apply(
            conn,
            {
                "ts": timeutil.to_iso(timeutil.utcnow()),
                "kind": "pr.tracked",
                "payload": {
                    "repo": "acme/app", "number": 2, "party": "alpha", "task_quest": "demo",
                    "task_tid": "T01", "what": "x", "waits": "y", "lifecycle": "needs-human",
                    "branch": None, "title": None, "gh_state": None, "gh_draft": None, "seeded": 1,
                },
            },
        )
        reducers.apply(
            conn,
            {
                "ts": timeutil.to_iso(timeutil.utcnow()),
                "kind": "pr.tracked",
                "payload": {
                    "repo": "acme/app", "number": 3, "party": "alpha", "task_quest": "demo",
                    "task_tid": "T01", "what": "x", "waits": "y", "lifecycle": "draft",
                    "needs_human_pr_review": 1,
                    "branch": None, "title": None, "gh_state": None, "gh_draft": None, "seeded": 0,
                },
            },
        )
        flagged = conn.execute("SELECT * FROM prs WHERE number = 3").fetchone()
        self.assertEqual((flagged["needs_ask_answer"], flagged["needs_human_pr_review"]), (0, 1))
        legacy = conn.execute("SELECT * FROM prs WHERE number = 2").fetchone()
        plain = conn.execute("SELECT * FROM prs WHERE number = 1").fetchone()
        conn.close()
        self.assertEqual(
            (legacy["lifecycle"], legacy["needs_ask_answer"], legacy["needs_human_pr_review"]), ("draft", 1, 0)
        )
        self.assertEqual((plain["needs_ask_answer"], plain["needs_human_pr_review"]), (0, 0))

    def test_acknowledge_comments_syncs_last_notified_count(self):
        self.write_gh_fixture(
            "view_acme-app_1",
            {
                "state": "OPEN", "isDraft": True, "headRefName": "feature/x", "title": "t",
                "comments": [{"id": 1}, {"id": 2}],
            },
        )
        self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)
        self.assertEqual(self._pr_row()["last_notified_comment_count"], 0)

        conn = db.connect(paths.db_path())
        ctx = RunContext(conn, "sess-1", self.repo_dir, timeutil.utcnow(), origin.current_origin(), None, None, None)
        pr_commands.acknowledge_comments(ctx, "acme/app", 1)
        conn.close()

        self.assertEqual(self._pr_row()["last_notified_comment_count"], 2)


if __name__ == "__main__":
    import unittest

    unittest.main()
