import sqlite3

from tests.test_fast_forward_base import _CloneFixture
from tests.testutil import GuildTestCase

_FAILED_RUNS = {
    "check_runs": [
        {"name": "lint", "conclusion": "failure"},
        {"name": "unit", "conclusion": "success"},
        {"name": "e2e", "conclusion": "timed_out"},
        {"name": "deploy", "conclusion": None},
    ]
}
_BILLING_TEXT = (
    "The job was not started because recent account payments have failed or your spending limit needs to be increased."
)
_BILLING_RUNS = {
    "check_runs": [
        {"id": 11, "name": "lint", "conclusion": "failure", "output": {"annotations_count": 1}},
        {"id": 12, "name": "unit", "conclusion": "failure", "output": {"annotations_count": 1}},
        {"id": 13, "name": "docs", "conclusion": "success", "output": {"annotations_count": 0}},
    ]
}
_MIXED_RUNS = {
    "check_runs": [
        {"id": 11, "name": "lint", "conclusion": "failure", "output": {"annotations_count": 1}},
        {"id": 12, "name": "unit", "conclusion": "failure", "output": {"annotations_count": 1}},
    ]
}
_FAST = {"started_at": "2026-01-01T00:00:00Z", "completed_at": "2026-01-01T00:00:02Z"}
_SLOW = {"started_at": "2026-01-01T00:00:00Z", "completed_at": "2026-01-01T00:01:30Z"}
_STEPLESS_RUNS = {
    "check_runs": [
        dict(_FAST, id=11, name="lint", conclusion="failure", output={"annotations_count": 0}),
        dict(_FAST, id=12, name="unit", conclusion="failure", output={"annotations_count": 0}),
        dict(_SLOW, id=13, name="docs", conclusion="success", output={"annotations_count": 0}),
    ]
}
_STEPLESS_AND_SLOW_RUNS = {
    "check_runs": [
        dict(_FAST, id=11, name="lint", conclusion="failure", output={"annotations_count": 0}),
        dict(_SLOW, id=12, name="unit", conclusion="failure", output={"annotations_count": 0}),
    ]
}
_FAST_WITH_ANNOTATION_RUNS = {
    "check_runs": [dict(_FAST, id=11, name="lint", conclusion="failure", output={"annotations_count": 1})]
}
_GREEN_RUNS = {"check_runs": [{"name": "unit", "conclusion": "success"}]}


class _MainStatusCase(GuildTestCase):
    def rows(self):
        conn = sqlite3.connect(str(self.data_home / "guild" / "guild.db"))
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM main_status ORDER BY repo, source").fetchall()
        conn.close()
        return [(row["repo"], row["source"], row["red"], row["reason"]) for row in rows]

    def event_kinds(self):
        conn = sqlite3.connect(str(self.data_home / "guild" / "guild.db"))
        kinds = [row[0] for row in conn.execute("SELECT kind FROM events ORDER BY seq").fetchall()]
        conn.close()
        return [kind for kind in kinds if kind.startswith("main.")]


class ManualMarkTests(_MainStatusCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])

    def test_red_records_a_manual_row(self):
        code, out, err = self.run_cli(["main", "red", "acme/app", "--reason", "ci down"], None, self.repo_dir)
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "marked main of 'acme/app' red: ci down")
        self.assertEqual(self.rows(), [("acme/app", "manual", 1, "ci down")])

    def test_green_clears_the_manual_row(self):
        self.run_cli(["main", "red", "acme/app", "--reason", "ci down"], None, self.repo_dir)
        code, out, err = self.run_cli(["main", "green", "acme/app"], None, self.repo_dir)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.rows(), [("acme/app", "manual", 0, None)])

    def test_red_requires_a_reason(self):
        code, out, err = self.run_cli(["main", "red", "acme/app"], None, self.repo_dir)
        self.assertEqual(code, 2)

    def test_red_rejects_an_empty_reason(self):
        code, out, err = self.run_cli(["main", "red", "acme/app", "--reason", "  "], None, self.repo_dir)
        self.assertEqual(code, 1)
        self.assertIn("--reason must not be empty", err)
        self.assertEqual(self.rows(), [])

    def test_unknown_repo_is_rejected(self):
        code, out, err = self.run_cli(["main", "red", "nope/x", "--reason", "r"], None, self.repo_dir)
        self.assertEqual(code, 1)
        self.assertIn("repo 'nope/x' does not belong to any configured project", err)

    def test_green_of_an_unknown_repo_is_rejected(self):
        code, out, err = self.run_cli(["main", "green", "nope/x"], None, self.repo_dir)
        self.assertEqual(code, 1)

    def test_bound_session_is_recorded_as_the_actor(self):
        self.run_cli(
            ["party", "start", "alpha", "--reason", "test reason", "--goal", "test goal", "--done-when", "test done"],
            "sess-1",
            self.repo_dir,
        )
        code, out, err = self.run_cli(["main", "red", "acme/app", "--reason", "x"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        conn = sqlite3.connect(str(self.data_home / "guild" / "guild.db"))
        party = conn.execute("SELECT party FROM events WHERE kind = 'main.marked'").fetchone()[0]
        conn.close()
        self.assertEqual(party, "alpha")

    def test_rebuild_replays_the_events(self):
        self.run_cli(["main", "red", "acme/app", "--reason", "ci down"], None, self.repo_dir)
        code, out, err = self.run_cli(["rebuild"], None, self.repo_dir)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.rows(), [("acme/app", "manual", 1, "ci down")])

    def test_rebuild_replays_green_after_red(self):
        self.run_cli(["main", "red", "acme/app", "--reason", "ci down"], None, self.repo_dir)
        self.run_cli(["main", "green", "acme/app"], None, self.repo_dir)
        self.run_cli(["rebuild"], None, self.repo_dir)
        self.assertEqual(self.rows(), [("acme/app", "manual", 0, None)])


class GhSyncTests(_CloneFixture, _MainStatusCase):
    def test_failing_base_checks_mark_main_red(self):
        self.write_gh_fixture("branch_checks_acme-app_main", _FAILED_RUNS)
        self._sync()
        self.assertEqual(self.rows(), [("acme/app", "gh", 1, "checks failing: e2e, lint")])

    def test_green_base_checks_clear_the_red_mark(self):
        self.write_gh_fixture("branch_checks_acme-app_main", _FAILED_RUNS)
        self._sync()
        self.write_gh_fixture("branch_checks_acme-app_main", _GREEN_RUNS)
        self._sync()
        self.assertEqual(self.rows(), [("acme/app", "gh", 0, None)])

    def test_unchanged_status_records_no_new_event(self):
        self.write_gh_fixture("branch_checks_acme-app_main", _FAILED_RUNS)
        self._sync()
        self._sync()
        self.assertEqual(self.event_kinds(), ["main.status_synced"])

    def test_green_main_from_the_start_records_nothing(self):
        self.write_gh_fixture("branch_checks_acme-app_main", _GREEN_RUNS)
        self._sync()
        self.assertEqual(self.rows(), [])
        self.assertEqual(self.event_kinds(), [])

    def test_gh_failure_is_reported_and_leaves_the_status_alone(self):
        self.write_gh_error("branch_checks_acme-app_main", "boom")
        code, out, err = self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)
        self.assertIn("acme/app: main status check failed: boom", out + err)
        self.assertEqual(self.rows(), [])

    def _run(self, workflow, conclusion, sha, run_id, event):
        status = "completed" if conclusion else "in_progress"
        return {
            "workflowName": workflow,
            "conclusion": conclusion,
            "status": status,
            "headSha": sha,
            "databaseId": run_id,
            "event": event,
        }

    def test_latest_failed_workflow_run_marks_main_red_when_head_has_no_failing_checks(self):
        self.write_gh_fixture("branch_checks_acme-app_main", _GREEN_RUNS)
        self.write_gh_fixture(
            "branch_runs_acme-app_main",
            [
                self._run("CI", "failure", "4cf88e46d0", 41, "workflow_dispatch"),
                self._run("CI", "success", "c6365058d0", 40, "schedule"),
                self._run("Docs", "success", "c6365058d0", 39, "schedule"),
            ],
        )
        self._sync()
        self.assertEqual(self.rows(), [("acme/app", "gh", 1, "workflow CI failed @ 4cf88e4 (run 41)")])

    def test_a_later_green_run_of_the_workflow_clears_the_red(self):
        self.write_gh_fixture("branch_checks_acme-app_main", _GREEN_RUNS)
        self.write_gh_fixture("branch_runs_acme-app_main", [self._run("CI", "failure", "4cf88e46d0", 41, "schedule")])
        self._sync()
        self.write_gh_fixture(
            "branch_runs_acme-app_main",
            [
                self._run("CI", "success", "12bb6740f0", 42, "schedule"),
                self._run("CI", "failure", "4cf88e46d0", 41, "schedule"),
            ],
        )
        self._sync()
        self.assertEqual(self.rows(), [("acme/app", "gh", 0, None)])

    def test_running_cancelled_and_skipped_runs_fall_back_to_the_previous_completed_one(self):
        self.write_gh_fixture("branch_checks_acme-app_main", _GREEN_RUNS)
        self.write_gh_fixture(
            "branch_runs_acme-app_main",
            [
                self._run("CI", "", "aaaaaaa000", 45, "schedule"),
                self._run("CI", "cancelled", "bbbbbbb000", 44, "schedule"),
                self._run("CI", "skipped", "ccccccc000", 43, "schedule"),
                self._run("CI", "failure", "ddddddd000", 42, "schedule"),
            ],
        )
        self._sync()
        self.assertEqual(self.rows(), [("acme/app", "gh", 1, "workflow CI failed @ ddddddd (run 42)")])

    def test_dependabot_update_runs_on_the_base_do_not_mark_main_red(self):
        self.write_gh_fixture("branch_checks_acme-app_main", _GREEN_RUNS)
        self.write_gh_fixture(
            "branch_runs_acme-app_main", [self._run("pip in /. - Update #1", "failure", "aaaaaaa000", 9, "dynamic")]
        )
        self._sync()
        self.assertEqual(self.rows(), [])

    def test_failing_dependabot_check_on_the_base_head_does_not_mark_main_red(self):
        self.write_gh_fixture(
            "branch_checks_acme-app_main",
            {
                "check_runs": [
                    {"name": "unit", "conclusion": "success"},
                    {"name": "Dependabot", "conclusion": "failure"},
                ]
            },
        )
        self._sync()
        self.assertEqual(self.rows(), [])

    def test_failing_head_checks_win_over_workflow_runs(self):
        self.write_gh_fixture("branch_checks_acme-app_main", _FAILED_RUNS)
        self.write_gh_fixture("branch_runs_acme-app_main", [self._run("CI", "failure", "aaaaaaa000", 9, "schedule")])
        self._sync()
        self.assertEqual(self.rows(), [("acme/app", "gh", 1, "checks failing: e2e, lint")])

    def test_workflow_runs_failure_is_reported_and_leaves_the_status_alone(self):
        self.write_gh_fixture("branch_checks_acme-app_main", _GREEN_RUNS)
        self.write_gh_error("branch_runs_acme-app_main", "boom")
        code, out, err = self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)
        self.assertIn("acme/app: main status check failed: boom", out + err)
        self.assertEqual(self.rows(), [])

    def _write_annotations(self, run_id, message):
        self.write_gh_fixture("annotations_acme-app_{}".format(run_id), [{"message": message}])

    def _external(self):
        conn = sqlite3.connect(str(self.data_home / "guild" / "guild.db"))
        rows = conn.execute("SELECT external FROM main_status ORDER BY repo, source").fetchall()
        conn.close()
        return [row[0] for row in rows]

    def test_every_failing_run_blocked_by_billing_marks_main_external(self):
        self.write_gh_fixture("branch_checks_acme-app_main", _BILLING_RUNS)
        self._write_annotations(11, _BILLING_TEXT)
        self._write_annotations(12, _BILLING_TEXT.upper())
        self._sync()
        self.assertEqual(self.rows(), [("acme/app", "gh", 1, "checks failing: lint, unit")])
        self.assertEqual(self._external(), ["billing"])

    def test_one_failing_run_without_billing_text_keeps_main_red(self):
        self.write_gh_fixture("branch_checks_acme-app_main", _MIXED_RUNS)
        self._write_annotations(11, _BILLING_TEXT)
        self._write_annotations(12, "Process completed with exit code 1.")
        self._sync()
        self.assertEqual(self._external(), [None])

    def test_fast_failing_runs_without_annotations_mark_main_external(self):
        self.write_gh_fixture("branch_checks_acme-app_main", _STEPLESS_RUNS)
        self._sync()
        self.assertEqual(self._external(), ["billing"])

    def test_slow_failing_run_without_annotations_keeps_main_red(self):
        self.write_gh_fixture("branch_checks_acme-app_main", _STEPLESS_AND_SLOW_RUNS)
        self._sync()
        self.assertEqual(self._external(), [None])

    def test_fast_failing_run_with_other_annotation_keeps_main_red(self):
        self.write_gh_fixture("branch_checks_acme-app_main", _FAST_WITH_ANNOTATION_RUNS)
        self._write_annotations(11, "Process completed with exit code 1.")
        self._sync()
        self.assertEqual(self._external(), [None])

    def test_failing_run_without_annotations_keeps_main_red(self):
        self.write_gh_fixture("branch_checks_acme-app_main", _FAILED_RUNS)
        self._sync()
        self.assertEqual(self._external(), [None])

    def test_billing_fixed_clears_the_external_mark(self):
        self.write_gh_fixture("branch_checks_acme-app_main", _BILLING_RUNS)
        self._write_annotations(11, _BILLING_TEXT)
        self._write_annotations(12, _BILLING_TEXT)
        self._sync()
        self.write_gh_fixture("branch_checks_acme-app_main", _GREEN_RUNS)
        self._sync()
        self.assertEqual(self.rows(), [("acme/app", "gh", 0, None)])
        self.assertEqual(self._external(), [None])

    def test_external_change_with_same_reason_records_a_new_event(self):
        self.write_gh_fixture("branch_checks_acme-app_main", _MIXED_RUNS)
        self._write_annotations(11, _BILLING_TEXT)
        self._write_annotations(12, "boom")
        self._sync()
        self._write_annotations(12, _BILLING_TEXT)
        self._sync()
        self._sync()
        self.assertEqual(self.event_kinds(), ["main.status_synced", "main.status_synced"])

    def test_rebuild_replays_the_external_mark(self):
        self.write_gh_fixture("branch_checks_acme-app_main", _BILLING_RUNS)
        self._write_annotations(11, _BILLING_TEXT)
        self._write_annotations(12, _BILLING_TEXT)
        self._sync()
        self.run_cli(["rebuild"], None, self.repo_dir)
        self.assertEqual(self._external(), ["billing"])

    def test_old_payload_without_external_replays_as_red(self):
        conn = sqlite3.connect(str(self.data_home / "guild" / "guild.db"))
        conn.execute(
            "INSERT INTO events (id, ts, origin, kind, visibility, payload) VALUES (?, ?, ?, ?, ?, ?)",
            (
                "old-1",
                "2026-01-01T00:00:00Z",
                "t",
                "main.status_synced",
                "guild",
                '{"repo": "acme/app", "red": true, "reason": "checks failing: lint"}',
            ),
        )
        conn.commit()
        conn.close()
        self.run_cli(["rebuild"], None, self.repo_dir)
        self.assertEqual(self._external(), [None])

    def test_billing_main_shows_as_blocked_in_the_merge_queue(self):
        self.write_gh_fixture("branch_checks_acme-app_main", _BILLING_RUNS)
        self._write_annotations(11, _BILLING_TEXT)
        self._write_annotations(12, _BILLING_TEXT)
        self._sync()
        code, out, err = self.run_cli(["merge-queue", "--party", "alpha"], None, self.repo_dir)
        self.assertIn("0. MAIN BLOCKED (billing) acme/app \u2192 re-run main once billing is fixed", out)
        self.assertNotIn("MAIN RED", out)

    def test_manual_and_gh_marks_coexist(self):
        self.write_gh_fixture("branch_checks_acme-app_main", _FAILED_RUNS)
        self._sync()
        self.run_cli(["main", "red", "acme/app", "--reason", "manual"], None, self.repo_dir)
        self.run_cli(["main", "green", "acme/app"], None, self.repo_dir)
        self.assertEqual(
            self.rows(),
            [("acme/app", "gh", 1, "checks failing: e2e, lint"), ("acme/app", "manual", 0, None)],
        )

    def test_rebuild_replays_the_gh_status(self):
        self.write_gh_fixture("branch_checks_acme-app_main", _FAILED_RUNS)
        self._sync()
        self.run_cli(["rebuild"], None, self.repo_dir)
        self.assertEqual(self.rows(), [("acme/app", "gh", 1, "checks failing: e2e, lint")])

    def test_red_gh_main_shows_in_the_merge_queue(self):
        self.write_gh_fixture("branch_checks_acme-app_main", _FAILED_RUNS)
        self._sync()
        code, out, err = self.run_cli(["merge-queue", "--party", "alpha"], None, self.repo_dir)
        self.assertIn("0. MAIN RED acme/app — checks failing: e2e, lint (gh) → fix before anything", out)


if __name__ == "__main__":
    import unittest

    unittest.main()
