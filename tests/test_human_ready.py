import shutil
import sys
import time
import unittest

from guild import human_ready
from tests.lifecycle_fixtures import init_clone
from tests.mq_fixtures import OPEN_VIEW, MergeQueueTestCase

_HEAD = "2026-10-20T10:00:00Z"


def _comment(login, created_at):
    return {"author": {"login": login}, "createdAt": created_at}


def _review(login, submitted_at):
    return {"author": {"login": login}, "submittedAt": submitted_at}


class CommentsAfterHeadTests(unittest.TestCase):
    def test_counts_only_strictly_later_entries(self):
        comments = [
            _comment("bot", "2026-10-20T09:59:59Z"),
            _comment("bot", _HEAD),
            _comment("bot", "2026-10-20T10:00:01Z"),
        ]
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


def _body(entry, text):
    return dict(entry, body=text)


_NOTICE_RULES = [{"author": "notifier", "text": "usage notice"}]


class OtherAuthorCommentsTests(unittest.TestCase):
    def _count(self, author, comments, reviews, rules):
        return human_ready.other_author_comments(author, comments, reviews, rules)

    def test_counts_entries_by_others_before_and_after_the_head(self):
        comments = [_comment("bot", "2026-10-20T09:00:00Z"), _comment("bot", "2026-10-20T11:00:00Z")]
        self.assertEqual(self._count("me", comments, [_review("bot", "2026-10-20T08:00:00Z")], []), 3)

    def test_excludes_the_pr_author(self):
        comments = [_comment("me", "2026-10-20T11:00:00Z"), _comment("bot", "2026-10-20T11:00:00Z")]
        self.assertEqual(self._count("me", comments, [], []), 1)

    def test_skips_entry_matching_rule_author_and_pattern(self):
        comments = [_body(_comment("notifier", _HEAD), "Usage notice: budget")]
        self.assertEqual(self._count("me", comments, [], _NOTICE_RULES), 0)

    def test_keeps_matching_body_by_another_author(self):
        comments = [_body(_comment("other", _HEAD), "Usage notice: budget")]
        self.assertEqual(self._count("me", comments, [], _NOTICE_RULES), 1)

    def test_keeps_rule_author_when_body_does_not_match(self):
        reviews = [_body(_review("notifier", _HEAD), "LGTM")]
        self.assertEqual(self._count("me", [], reviews, _NOTICE_RULES), 1)

    def test_review_without_body_is_kept(self):
        self.assertEqual(self._count("me", [], [_review("notifier", _HEAD)], _NOTICE_RULES), 1)

    def test_author_match_ignores_case(self):
        comments = [_body(_comment("Notifier", _HEAD), "Usage notice: budget")]
        self.assertEqual(self._count("me", comments, [], _NOTICE_RULES), 0)

    def test_no_pr_author_counts_everything(self):
        comments = [_comment("me", _HEAD), _comment("bot", _HEAD)]
        self.assertEqual(self._count(None, comments, [], []), 2)

    def test_text_matches_body_in_a_different_case(self):
        comments = [_body(_comment("notifier", _HEAD), "USAGE NOTICE: budget")]
        self.assertEqual(self._count("me", comments, [], _NOTICE_RULES), 0)

    def test_hostile_long_body_from_rule_author_returns_promptly(self):
        comments = [_body(_comment("notifier", _HEAD), "a" * 100000 + "b")]
        started = time.monotonic()
        self.assertEqual(self._count("me", comments, [], _NOTICE_RULES), 1)
        self.assertLess(time.monotonic() - started, 5)

    def test_text_beyond_two_thousand_characters_still_matches(self):
        comments = [_body(_comment("notifier", _HEAD), "x" * 5000 + "usage notice")]
        self.assertEqual(self._count("me", comments, [], _NOTICE_RULES), 0)


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
        commits = [
            {"oid": "head", "committedDate": "2026-10-20T10:30:00Z"},
            {"oid": "old", "committedDate": "2026-10-20T12:00:00Z"},
        ]
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

    def test_stores_other_author_comments_excluding_notice_rules(self):
        self._set_project_config({"human_ready": {"notice_comments": [{"author": "bot", "text": "usage"}]}})
        notice = _body(_comment("bot", "2026-10-20T11:00:00Z"), "Usage notice")
        real = _body(_comment("human", "2026-10-20T09:00:00Z"), "please fix")
        self._view(comments=[notice, real, _comment("me", "2026-10-20T11:00:00Z")], reviews=[])
        self.sync_gh("sess-1")
        count = self.query("SELECT other_author_comments FROM prs WHERE number = 1")[0]
        self.assertEqual(count["other_author_comments"], 1)

    def test_other_author_comments_survive_rebuild(self):
        self._view()
        self.sync_gh("sess-1")
        before = self.query("SELECT other_author_comments FROM prs WHERE number = 1")[0][0]
        self.assertEqual(before, 2)
        self.run_cli(["rebuild"], None, None)
        self.assertEqual(self.query("SELECT other_author_comments FROM prs WHERE number = 1")[0][0], 2)

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
    return {
        "id": run_id,
        "name": "job{}".format(run_id),
        "conclusion": conclusion,
        "output": {"annotations_count": annotations},
    }


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
        self._view(
            statusCheckRollup=[
                {"__typename": "CheckRun", "conclusion": "FAILURE"},
                {"__typename": "StatusContext", "state": "FAILURE"},
            ]
        )
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


_TRACE_SHA = "c" * 40
_VALIDATOR_SCRIPT = """import pathlib, sys
here = pathlib.Path(sys.argv[0]).parent
(here / "ran").write_text(" ".join(sys.argv[1:3]))
code = int((here / "code").read_text())
print((here / "message").read_text())
sys.exit(code)
"""


class TraceValidatorSyncTests(MergeQueueTestCase):
    def setUp(self):
        super().setUp()
        init_clone(self.repo_dir, "acme/app")
        self.scripts = self.root / "validator"
        self.scripts.mkdir()
        self.script = self.scripts / "validate.py"
        self.script.write_text(_VALIDATOR_SCRIPT)
        self._verdict(0, "")
        self.start_party("alpha", "sess-1")
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", self.repo_dir)
        self.run_cli(["task", "add", "demo/T01", "--title", "First"], "sess-1", self.repo_dir)
        self.track("sess-1", 1, "demo/T01", "ready")

    def _verdict(self, code, message):
        (self.scripts / "code").write_text(str(code))
        (self.scripts / "message").write_text(message)

    def _configure(self):
        command = [sys.executable, "-I", str(self.script), "{head_sha}", "{pr}", "{comments_file}"]
        self._set_project_config({"human_ready": {"trace_validator": {"command": command, "timeout_seconds": 30}}})

    def _view(self, **extra):
        self.write_gh_fixture("view_acme-app_1", dict(OPEN_VIEW, headRefOid=_TRACE_SHA, **extra))

    def _trace(self):
        row = self.query("SELECT trace_valid, trace_reason FROM prs WHERE number = 1")[0]
        return row["trace_valid"], row["trace_reason"]

    def _ran(self):
        return (self.scripts / "ran").exists()

    def test_ready_pr_stores_valid(self):
        self._configure()
        self._view()
        self.assertEqual(self.sync_gh("sess-1")[0], 0)
        self.assertEqual(self._trace(), (1, None))
        self.assertEqual((self.scripts / "ran").read_text(), _TRACE_SHA + " 1")

    def test_ready_pr_stores_invalid_with_reason(self):
        self._configure()
        self._verdict(1, "no trace for head")
        self._view()
        self.sync_gh("sess-1")
        self.assertEqual(self._trace(), (0, "no trace for head"))

    def test_draft_pr_is_not_validated(self):
        self._configure()
        self._view(isDraft=True)
        self.sync_gh("sess-1")
        self.assertEqual(self._trace(), (None, None))
        self.assertFalse(self._ran())

    def test_without_config_nothing_runs(self):
        self._view()
        self.sync_gh("sess-1")
        self.assertEqual(self._trace(), (None, None))
        self.assertFalse(self._ran())

    def test_missing_clone_is_not_validated(self):
        self._configure()
        shutil.rmtree(str(self.repo_dir / ".git"))
        self._view()
        self.assertEqual(self.sync_gh("sess-1")[0], 0)
        self.assertEqual(self._trace(), (None, "no local clone of acme/app"))
        self.assertFalse(self._ran())

    def test_validator_failure_does_not_fail_the_sync(self):
        self._set_project_config(
            {"human_ready": {"trace_validator": {"command": ["/nonexistent/validator"], "timeout_seconds": 30}}}
        )
        self._view()
        code, out, err = self.sync_gh("sess-1")
        self.assertEqual(code, 0, err)
        self.assertEqual(self._trace(), (None, "validator could not start"))
        self.assertEqual(self.query("SELECT lifecycle FROM prs WHERE number = 1")[0]["lifecycle"], "ready")

    def test_trace_change_keeps_last_activity(self):
        self._configure()
        self._view()
        self.sync_gh("sess-1")
        before = self.query("SELECT last_activity_at FROM prs WHERE number = 1")[0]["last_activity_at"]
        self._verdict(1, "stale")
        self.sync_gh("sess-1")
        self.assertEqual(self._trace(), (0, "stale"))
        self.assertEqual(self.query("SELECT last_activity_at FROM prs WHERE number = 1")[0]["last_activity_at"], before)

    def test_rebuild_reproduces_without_running_the_validator(self):
        self._configure()
        self._verdict(1, "no trace")
        self._view()
        self.sync_gh("sess-1")
        self.script.unlink()
        (self.scripts / "ran").unlink()
        code, out, err = self.run_cli(["rebuild"], None, None)
        self.assertEqual(code, 0, err)
        self.assertEqual(self._trace(), (0, "no trace"))
        self.assertFalse(self._ran())

    def test_removing_the_config_clears_the_trace(self):
        self._configure()
        self._view()
        self.sync_gh("sess-1")
        self._set_project_config({"human_ready": {}})
        self.sync_gh("sess-1")
        self.assertEqual(self._trace(), (None, None))
