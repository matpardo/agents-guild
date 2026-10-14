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
_BILLING_TEXT = "The job was not started because recent account payments have failed or your spending limit needs to be increased."
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
        self.run_cli(["party", "start", "alpha"], "sess-1", self.repo_dir)
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
            ("old-1", "2026-01-01T00:00:00Z", "t", "main.status_synced", "guild",
             '{"repo": "acme/app", "red": true, "reason": "checks failing: lint"}'),
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
        self.assertIn(
            "0. MAIN RED acme/app — checks failing: e2e, lint (gh) → fix before anything", out
        )


if __name__ == "__main__":
    import unittest

    unittest.main()
