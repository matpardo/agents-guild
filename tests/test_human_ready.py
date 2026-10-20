import json
import sqlite3
import unittest

from guild import human_ready
from tests.mq_fixtures import OPEN_VIEW, MergeQueueTestCase

_HEAD = "2026-10-20T10:00:00Z"


def _comment(login, created_at):
    return {"author": {"login": login}, "createdAt": created_at}


def _review(login, submitted_at):
    return {"author": {"login": login}, "submittedAt": submitted_at}


class CommentsAfterHeadTests(unittest.TestCase):
    def test_counts_only_strictly_later_entries(self):
        comments = [_comment("bot", "2026-10-20T09:59:59Z"), _comment("bot", _HEAD), _comment("bot", "2026-10-20T10:00:01Z")]
        self.assertEqual(human_ready.comments_after_head(_HEAD, "me", comments, []), 1)

    def test_excludes_the_pr_author(self):
        comments = [_comment("me", "2026-10-20T11:00:00Z"), _comment("bot", "2026-10-20T11:00:00Z")]
        self.assertEqual(human_ready.comments_after_head(_HEAD, "me", comments, []), 1)

    def test_counts_reviews_by_submitted_at(self):
        reviews = [_review("bot", "2026-10-20T11:00:00Z"), _review("me", "2026-10-20T11:00:00Z")]
        self.assertEqual(human_ready.comments_after_head(_HEAD, "me", [], reviews), 1)

    def test_pr_without_author_counts_everything(self):
        comments = [_comment("me", "2026-10-20T11:00:00Z"), _comment("bot", "2026-10-20T11:00:00Z")]
        self.assertEqual(human_ready.comments_after_head(_HEAD, None, comments, []), 2)

    def test_without_commits_is_unknown(self):
        self.assertIsNone(human_ready.comments_after_head(None, "me", [_comment("bot", _HEAD)], []))

    def test_deleted_author_counts_as_another_author(self):
        comments = [{"author": None, "createdAt": "2026-10-20T11:00:00Z"}]
        self.assertEqual(human_ready.comments_after_head(_HEAD, "me", comments, []), 1)


class HeadCommitDateTests(unittest.TestCase):
    def test_picks_the_commit_matching_the_head_even_if_unordered(self):
        commits = [
            {"oid": "b", "committedDate": "2026-10-20T10:00:00Z"},
            {"oid": "a", "committedDate": "2026-10-20T12:00:00Z"},
        ]
        self.assertEqual(human_ready.head_commit_date(commits, "b"), "2026-10-20T10:00:00Z")

    def test_falls_back_to_the_latest_date_when_head_is_missing(self):
        commits = [
            {"oid": "a", "committedDate": "2026-10-20T12:00:00Z"},
            {"oid": "b", "committedDate": "2026-10-20T10:00:00Z"},
        ]
        self.assertEqual(human_ready.head_commit_date(commits, "zzz"), "2026-10-20T12:00:00Z")

    def test_none_without_commits(self):
        self.assertIsNone(human_ready.head_commit_date([], "a"))

    def test_falls_back_to_the_latest_date_without_head_sha(self):
        commits = [{"oid": "a", "committedDate": "2026-10-20T12:00:00Z"}]
        self.assertEqual(human_ready.head_commit_date(commits, None), "2026-10-20T12:00:00Z")

    def test_falls_back_when_the_head_commit_has_no_date(self):
        commits = [{"oid": "a", "committedDate": "2026-10-20T12:00:00Z"}, {"oid": "b", "committedDate": None}]
        self.assertEqual(human_ready.head_commit_date(commits, "b"), "2026-10-20T12:00:00Z")


class CiLabelFlagTests(unittest.TestCase):
    def test_none_without_config(self):
        self.assertIsNone(human_ready.ci_label_flag({"name": "acme"}, [{"name": "run-ci"}]))

    def test_none_without_project(self):
        self.assertIsNone(human_ready.ci_label_flag(None, []))

    def test_label_match_ignores_case(self):
        project = {"human_ready": {"ci_label": "Run-CI"}}
        self.assertEqual(human_ready.ci_label_flag(project, [{"name": "run-ci"}]), 1)

    def test_flag_follows_label_presence(self):
        project = {"human_ready": {"ci_label": "run-ci"}}
        self.assertEqual(human_ready.ci_label_flag(project, [{"name": "run-ci"}]), 1)
        self.assertEqual(human_ready.ci_label_flag(project, [{"name": "other"}]), 0)


class SyncFreshnessFactsTests(MergeQueueTestCase):
    def setUp(self):
        super().setUp()
        self.start_party("alpha", "sess-1")
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", self.repo_dir)
        self.run_cli(["task", "add", "demo/T01", "--title", "First"], "sess-1", self.repo_dir)
        self.track("sess-1", 1, "demo/T01", "ready")

    def _view(self, **extra):
        view = dict(
            OPEN_VIEW,
            author={"login": "me"},
            labels=[{"name": "run-ci"}],
            commits=[{"committedDate": _HEAD}],
            comments=[_comment("bot", "2026-10-20T11:00:00Z"), _comment("me", "2026-10-20T11:00:00Z")],
            reviews=[_review("bot", "2026-10-20T09:00:00Z")],
        )
        view.update(extra)
        self.write_gh_fixture("view_acme-app_1", view)

    def _row(self):
        return self.query("SELECT comments_after_head, ci_label FROM prs WHERE number = 1")[0]

    def _set_ci_label(self):
        self._set_project_config({"human_ready": {"ci_label": "run-ci"}})

    def test_stores_comment_count_and_no_label_flag_without_config(self):
        self._view()
        self.assertEqual(self.sync_gh("sess-1")[0], 0)
        row = self._row()
        self.assertEqual(row["comments_after_head"], 1)
        self.assertIsNone(row["ci_label"])

    def test_stores_label_flag_when_configured(self):
        self._set_ci_label()
        self._view()
        self.sync_gh("sess-1")
        self.assertEqual(self._row()["ci_label"], 1)
        self._view(labels=[])
        self.sync_gh("sess-1")
        self.assertEqual(self._row()["ci_label"], 0)

    def test_counts_after_the_head_commit_picked_by_sha(self):
        commits = [{"oid": "head", "committedDate": "2026-10-20T10:30:00Z"}, {"oid": "old", "committedDate": "2026-10-20T12:00:00Z"}]
        self._view(headRefOid="head", commits=commits, reviews=[_review("bot", "2026-10-20T10:45:00Z")])
        self.sync_gh("sess-1")
        self.assertEqual(self._row()["comments_after_head"], 2)

    def test_no_commits_stores_null(self):
        self._view(commits=[])
        self.sync_gh("sess-1")
        self.assertIsNone(self._row()["comments_after_head"])

    def test_fact_only_changes_keep_last_activity(self):
        self._set_ci_label()
        self._view()
        self.sync_gh("sess-1")
        before = self.query("SELECT last_activity_at FROM prs WHERE number = 1")[0]["last_activity_at"]
        self._view(labels=[], commits=[{"oid": "x", "committedDate": "2026-10-20T12:00:00Z"}])
        self.sync_gh("sess-1")
        after = self.query("SELECT last_activity_at, comments_after_head, ci_label FROM prs WHERE number = 1")[0]
        self.assertEqual((after["comments_after_head"], after["ci_label"]), (0, 0))
        self.assertEqual(after["last_activity_at"], before)

    def test_rebuild_reproduces_the_columns(self):
        self._set_ci_label()
        self._view()
        self.sync_gh("sess-1")
        before = dict(self._row())
        code, out, err = self.run_cli(["rebuild"], None, None)
        self.assertEqual(code, 0, err)
        self.assertEqual(dict(self._row()), before)


_BILLING_TEXT = "The job was not started because recent account payments have failed."
_FAILING_ROLLUP = [{"conclusion": "FAILURE"}, {"conclusion": "FAILURE"}]


def _run(run_id, conclusion, annotations):
    return {"id": run_id, "name": "job{}".format(run_id), "conclusion": conclusion, "output": {"annotations_count": annotations}}


class ChecksBillingTests(MergeQueueTestCase):
    def setUp(self):
        super().setUp()
        self.start_party("alpha", "sess-1")
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", self.repo_dir)
        self.run_cli(["task", "add", "demo/T01", "--title", "First"], "sess-1", self.repo_dir)
        self.track("sess-1", 1, "demo/T01", "ready")

    def _view(self, **extra):
        view = dict(OPEN_VIEW, statusCheckRollup=_FAILING_ROLLUP, headRefOid="head")
        view.update(extra)
        self.write_gh_fixture("view_acme-app_1", view)

    def _runs(self, runs):
        self.write_gh_fixture("branch_checks_acme-app_head", {"check_runs": runs})

    def _annotate(self, run_id, message):
        self.write_gh_fixture("annotations_acme-app_{}".format(run_id), [{"message": message}])

    def _value(self):
        return self.query("SELECT checks_billing FROM prs WHERE number = 1")[0]["checks_billing"]

    def test_all_failing_runs_billing_stores_one(self):
        self._view()
        self._runs([_run(11, "failure", 1), _run(12, "failure", 1), _run(13, "success", 0)])
        self._annotate(11, _BILLING_TEXT)
        self._annotate(12, _BILLING_TEXT)
        self.assertEqual(self.sync_gh("sess-1")[0], 0)
        self.assertEqual(self._value(), 1)

    def test_mixed_failures_store_zero(self):
        self._view()
        self._runs([_run(11, "failure", 1), _run(12, "failure", 1)])
        self._annotate(11, _BILLING_TEXT)
        self._annotate(12, "tests failed")
        self.sync_gh("sess-1")
        self.assertEqual(self._value(), 0)

    def test_failing_run_without_annotations_stores_zero(self):
        self._view()
        self._runs([_run(11, "failure", 0)])
        self.sync_gh("sess-1")
        self.assertEqual(self._value(), 0)

    def test_failing_status_context_beside_billing_run_stores_zero(self):
        self._view(statusCheckRollup=[
            {"__typename": "CheckRun", "conclusion": "FAILURE"},
            {"__typename": "StatusContext", "state": "FAILURE"},
        ])
        self._runs([_run(11, "failure", 1)])
        self._annotate(11, _BILLING_TEXT)
        self.sync_gh("sess-1")
        self.assertEqual(self._value(), 0)

    def test_failing_runs_beyond_first_page_store_zero(self):
        self._view()
        self._runs([_run(11, "failure", 1)])
        self._annotate(11, _BILLING_TEXT)
        self.sync_gh("sess-1")
        self.assertEqual(self._value(), 0)

    def test_no_failing_checks_stores_null(self):
        self._view(statusCheckRollup=[{"conclusion": "SUCCESS"}])
        self.assertEqual(self.sync_gh("sess-1")[0], 0)
        self.assertIsNone(self._value())

    def test_missing_head_sha_stores_zero(self):
        self._view(headRefOid=None)
        self.assertEqual(self.sync_gh("sess-1")[0], 0)
        self.assertEqual(self._value(), 0)

    def test_gh_error_stores_zero_and_reports(self):
        self._view()
        code, out, err = self.sync_gh("sess-1")
        self.assertNotEqual(code, 0)
        self.assertIn("billing check failed", out + err)
        self.assertEqual(self._value(), 0)

    def test_flag_change_keeps_last_activity(self):
        self._view()
        self._runs([_run(11, "failure", 1)])
        self._annotate(11, _BILLING_TEXT)
        self.sync_gh("sess-1")
        before = self.query("SELECT last_activity_at FROM prs WHERE number = 1")[0]["last_activity_at"]
        self._annotate(11, "tests failed")
        self.sync_gh("sess-1")
        self.assertEqual(self._value(), 0)
        self.assertEqual(self.query("SELECT last_activity_at FROM prs WHERE number = 1")[0]["last_activity_at"], before)

    def test_rebuild_reproduces_the_column(self):
        self._view()
        self._runs([_run(11, "failure", 1), _run(12, "failure", 1)])
        self._annotate(11, _BILLING_TEXT)
        self._annotate(12, _BILLING_TEXT)
        self.sync_gh("sess-1")
        code, out, err = self.run_cli(["rebuild"], None, None)
        self.assertEqual(code, 0, err)
        self.assertEqual(self._value(), 1)
