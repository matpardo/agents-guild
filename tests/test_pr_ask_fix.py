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
            {"repo": "acme/app", "number": 1, "party": "alpha", "reasons": ["checks failing (1)"]},
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

    def request_column(self):
        return self.query("SELECT fix_requested_at FROM prs")[0]["fix_requested_at"]

    def assert_refused_while_open(self):
        code, out, err = self.ask_fix()
        self.assertEqual(code, 1)
        self.assertIn("fix already requested 0h ago; waiting on alpha", err)
        self.assertEqual(len(self.events()), 1)
        self.assertEqual(len(self.notices()), 1)

    def test_request_opens_the_tag_and_a_second_request_is_refused(self):
        self.sync_view(_FAILING_VIEW)
        self.ask_fix()
        self.assertIsNotNone(self.request_column())
        self.assert_refused_while_open()

    def test_partial_push_keeps_the_tag(self):
        self.sync_view(_FAILING_VIEW)
        self.ask_fix()
        self.sync_view(dict(_FAILING_VIEW, headRefOid="def456"))
        self.assertIsNotNone(self.request_column())
        self.assert_refused_while_open()

    def test_cleared_blockers_close_the_tag(self):
        self.sync_view(_FAILING_VIEW)
        self.ask_fix()
        self.sync_view(dict(OPEN_VIEW, headRefOid="def456"))
        self.assertIsNone(self.request_column())
        self.sync_view(_FAILING_VIEW)
        self.assertIsNone(self.request_column())

    def test_merge_closes_the_tag(self):
        self.sync_view(_FAILING_VIEW)
        self.ask_fix()
        self.sync_view(dict(_FAILING_VIEW, state="MERGED", mergedAt="2026-10-11T10:00:00Z"))
        self.assertIsNone(self.request_column())

    def test_stale_request_with_config_allows_a_new_one(self):
        self._set_project_config({"fix_request_stale_hours": 4})
        self.sync_view(_FAILING_VIEW)
        self.ask_fix()
        self.backdate_fix_request(3)
        code, out, err = self.ask_fix()
        self.assertEqual(code, 1)
        self.assertIn("fix already requested 3h ago; waiting on alpha", err)
        self.backdate_fix_request(5)
        code, out, err = self.ask_fix()
        self.assertEqual(code, 0, err)
        self.assertEqual(len(self.events()), 2)

    def test_request_without_config_never_goes_stale(self):
        self.sync_view(_FAILING_VIEW)
        self.ask_fix()
        self.backdate_fix_request(24 * 365)
        code, out, err = self.ask_fix()
        self.assertEqual(code, 1)
        self.assertIn("fix already requested 8760h ago; waiting on alpha", err)

    def test_invalid_stale_hours_config_is_rejected(self):
        self.sync_view(_FAILING_VIEW)
        self._set_project_config({"fix_request_stale_hours": 0})
        code, out, err = self.ask_fix()
        self.assertEqual(code, 1)
        self.assertIn("fix_request_stale_hours", err)

    def test_ready_check_shows_the_tag(self):
        self.sync_view(_FAILING_VIEW)
        self.ask_fix()
        code, out, err = self.run_cli(["pr", "ready-check", _REF], None, self.repo_dir)
        self.assertIn("- fixing \u00b7 alpha \u00b7 0h", out)

    def test_board_and_merge_queue_show_the_tag(self):
        self.sync_view(_FAILING_VIEW)
        self.ask_fix()
        code, out, err = self.run_cli(["merge-queue", "--party", "alpha"], None, self.repo_dir)
        self.assertIn("[fixing \u00b7 alpha \u00b7 0h]", out)
        code, out, err = self.run_cli(["board"], "sess-1", self.repo_dir)
        self.assertIn("fixing \u00b7 alpha \u00b7 0h", out)

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

    def test_untracked_pr_is_refused(self):
        code, out, err = self.run_cli(["pr", "ask-fix", "acme/app#9"], None, self.repo_dir)
        self.assertEqual(code, 1)
        self.assertIn("not tracked", err)

    def test_rebuild_restores_the_request_marker(self):
        self.sync_view(_FAILING_VIEW)
        self.ask_fix()
        marker = self.request_column()
        self.run_cli(["rebuild"], None, self.repo_dir)
        self.assertEqual(self.request_column(), marker)
        self.assert_refused_while_open()
