import json

from tests.mq_fixtures import OPEN_VIEW
from tests.mq_fixtures import MergeQueueTestCase

_REF = "acme/app#1"
_FAILING_VIEW = dict(OPEN_VIEW, statusCheckRollup=[{"conclusion": "FAILURE"}], headRefOid="abc123")


class AskFixTestCase(MergeQueueTestCase):
    def setUp(self):
        super().setUp()
        self.start_party("alpha", "sess-1")
        self.run_cli(["quest", "add", "qa", "--title", "qa", "--no-epic"], "sess-1", self.repo_dir)
        self.run_cli(["task", "add", "qa/T01", "--title", "T01"], "sess-1", self.repo_dir)
        self.track("sess-1", 1, "qa/T01", "ready")

    def sync_view(self, view):
        self.write_gh_fixture("view_acme-app_1", view)
        code, out, err = self.sync_gh("sess-1")
        self.assertEqual(code, 0, err)

    def ask_fix(self):
        return self.run_cli(["pr", "ask-fix", _REF], None, self.repo_dir)

    def events(self):
        return self.query("SELECT party, project, payload FROM events WHERE kind = 'pr.fix_requested'")

    def notices(self):
        return self.query("SELECT text, scope FROM notices WHERE text LIKE '%fix acme/app#1%'")

    def test_request_records_event_and_notice_without_a_bound_party(self):
        self.sync_view(_FAILING_VIEW)
        code, out, err = self.ask_fix()
        self.assertEqual(code, 0, err)
        events = self.events()
        self.assertEqual(len(events), 1)
        self.assertIsNone(events[0]["party"])
        self.assertEqual(events[0]["project"], "acme")
        self.assertEqual(
            json.loads(events[0]["payload"]),
            {"repo": "acme/app", "number": 1, "party": "alpha", "reasons": ["checks failing (1)"], "head_sha": "abc123"},
        )
        notices = self.notices()
        self.assertEqual(len(notices), 1)
        self.assertEqual(notices[0]["text"], "alpha: fix acme/app#1: checks failing (1)")
        self.assertEqual(notices[0]["scope"], "project:acme")

    def test_review_reasons_are_listed(self):
        self.sync_view(dict(_FAILING_VIEW, mergeable="CONFLICTING", reviewDecision="CHANGES_REQUESTED"))
        self.ask_fix()
        self.assertEqual(
            self.notices()[0]["text"],
            "alpha: fix acme/app#1: checks failing (1), merge conflict, changes requested",
        )

    def test_second_request_for_the_same_commit_is_deduped(self):
        self.sync_view(_FAILING_VIEW)
        self.ask_fix()
        code, out, err = self.ask_fix()
        self.assertEqual(code, 0, err)
        self.assertIn("already requested for this commit", out)
        self.assertEqual(len(self.events()), 1)
        self.assertEqual(len(self.notices()), 1)

    def test_new_head_allows_a_new_request(self):
        self.sync_view(_FAILING_VIEW)
        self.ask_fix()
        self.sync_view(dict(_FAILING_VIEW, headRefOid="def456"))
        code, out, err = self.ask_fix()
        self.assertEqual(code, 0, err)
        self.assertEqual(len(self.events()), 2)

    def test_pr_without_automatic_blockers_is_refused(self):
        self.sync_view(dict(OPEN_VIEW, headRefOid="abc123"))
        code, out, err = self.ask_fix()
        self.assertEqual(code, 1)
        self.assertIn("no automatic blockers", err)
        self.assertEqual(self.events(), [])

    def test_manually_blocked_pr_is_refused(self):
        self.sync_view(_FAILING_VIEW)
        self.run_cli(["pr", "set", _REF, "--blocked-external", "legal"], "sess-1", self.repo_dir)
        code, out, err = self.ask_fix()
        self.assertEqual(code, 1)
        self.assertIn("unblock it first", err)
        self.assertEqual(self.events(), [])

    def test_closed_pr_is_refused(self):
        self.sync_view(_FAILING_VIEW)
        self.sync_view(dict(_FAILING_VIEW, state="CLOSED"))
        code, out, err = self.ask_fix()
        self.assertEqual(code, 1)
        self.assertIn("closed", err)

    def test_unsynced_head_is_refused(self):
        self.sync_view(dict(_FAILING_VIEW, headRefOid=None))
        code, out, err = self.ask_fix()
        self.assertEqual(code, 1)
        self.assertIn("no synced head commit", err)

    def test_untracked_pr_is_refused(self):
        code, out, err = self.run_cli(["pr", "ask-fix", "acme/app#9"], None, self.repo_dir)
        self.assertEqual(code, 1)
        self.assertIn("not tracked", err)

    def test_rebuild_restores_the_request_marker(self):
        self.sync_view(_FAILING_VIEW)
        self.ask_fix()
        self.run_cli(["rebuild"], None, self.repo_dir)
        code, out, err = self.ask_fix()
        self.assertIn("already requested for this commit", out)
