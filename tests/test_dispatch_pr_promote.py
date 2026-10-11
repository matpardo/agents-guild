from guild import db, paths
from tests.test_dispatch_checks_failing import ChecksFailingBase
from tests.test_dispatch_checks_failing import _FAILING, _FAILING_AND_PENDING, _PASSING


class PromoteTests(ChecksFailingBase):
    def setUp(self):
        super().setUp()
        self.write_block({"pr_promote": "on"})
        self.write_gh_fixture("ready_acme-app_1", {})
        self.pr_set("--lifecycle", "converging")

    def pr_set(self, *flags):
        self.run_cli(["party", "resume", "alpha"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["pr", "set", "acme/app#1"] + list(flags), "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        self.run_cli(["handoff", "--in-flight", "x", "--learned", "y"], "sess-1", self.repo_dir)

    def sync_green(self, head_sha):
        self.sync_open(_PASSING, head_sha)

    def ready_calls(self):
        log = self.gh_fixtures_dir / "ready_calls.log"
        return log.read_text().splitlines() if log.exists() else []

    def notice_lines(self):
        code, out, err = self.run_cli(["notices"], "sess-1", self.repo_dir)
        return [line for line in out.splitlines() if "acme/app#1" in line]

    def test_green_converging_draft_is_promoted_once_per_head(self):
        self.sync_green("abc123")
        self.assertEqual(self.run_pass(), ["acme: pr_promote acme/app#1 -> promoted alpha"])
        self.assertEqual(self.ready_calls(), ["acme/app 1"])
        self.assertEqual(self.decision_keys(), ["pr_promote:acme/app#1:abc123"])
        self.assertEqual(len(self.notice_lines()), 1)
        self.assertIn("acme/app#1 promoted to ready", self.notice_lines()[0])
        self.sync_green("abc123")
        self.assertEqual(self.run_pass(), ["nothing to dispatch"])
        self.assertEqual(self.ready_calls(), ["acme/app 1"])

    def test_new_head_promotes_again(self):
        self.sync_green("abc123")
        self.run_pass()
        self.sync_green("def456")
        self.assertEqual(len(self.run_pass()), 1)
        self.assertEqual(self.ready_calls(), ["acme/app 1", "acme/app 1"])

    def test_pr_needing_human_review_is_only_notified(self):
        self.pr_set("--needs-human-pr-review")
        self.sync_green("abc123")
        self.assertEqual(self.run_pass(), ["acme: pr_promote acme/app#1 -> notified alpha"])
        self.assertEqual(self.ready_calls(), [])
        self.assertIn("acme/app#1 converged; needs human review before ready", self.notice_lines()[0])

    def test_dry_run_records_a_plan_without_calling_gh(self):
        self.write_block({"pr_promote": "dry-run"})
        self.sync_green("abc123")
        self.assertEqual(self.run_pass(), ["acme: pr_promote acme/app#1 -> planned: promote alpha"])
        self.assertEqual(self.ready_calls(), [])
        self.assertEqual(self.notice_lines(), [])

    def test_gh_failure_records_a_failed_decision_and_a_notice(self):
        (self.gh_fixtures_dir / "ready_acme-app_1.json").unlink()
        self.write_gh_error("ready_acme-app_1", "boom")
        self.sync_green("abc123")
        self.assertEqual(self.run_pass(), ["acme: pr_promote acme/app#1 -> failed alpha: boom"])
        self.assertIn("could not mark acme/app#1 ready: boom", self.notice_lines()[0])
        self.sync_green("abc123")
        self.assertEqual(self.run_pass(), ["nothing to dispatch"])

    def test_pending_checks_do_nothing(self):
        self.sync_open(_PASSING + _FAILING_AND_PENDING[1:], "abc123")
        self.assertEqual(self.run_pass(), ["nothing to dispatch"])

    def test_failing_checks_do_nothing(self):
        self.sync_open(_PASSING + _FAILING, "abc123")
        self.assertEqual(self.run_pass(), ["nothing to dispatch"])

    def test_no_checks_do_nothing(self):
        self.sync_open([], "abc123")
        self.assertEqual(self.run_pass(), ["nothing to dispatch"])

    def test_review_reasons_do_nothing(self):
        self.sync_open(_PASSING, "abc123")
        self.write_gh_fixture(
            "view_acme-app_1",
            {
                "state": "OPEN", "isDraft": True, "headRefName": "feature/x", "title": "t",
                "statusCheckRollup": _PASSING, "headRefOid": "def456", "mergeable": "CONFLICTING",
            },
        )
        self.run_cli(["sync", "--source", "gh"], None, self.repo_dir)
        self.assertEqual(self.run_pass(), ["nothing to dispatch"])

    def test_pending_ask_does_nothing(self):
        self.pr_set("--needs-ask-answer")
        self.sync_green("abc123")
        self.assertEqual(self.run_pass(), ["nothing to dispatch"])

    def test_external_block_does_nothing(self):
        self.pr_set("--blocked-external", "decision")
        self.sync_green("abc123")
        self.assertEqual(self.run_pass(), ["nothing to dispatch"])

    def test_ready_lifecycle_does_nothing(self):
        self.pr_set("--lifecycle", "ready")
        self.sync_green("abc123")
        self.assertEqual(self.run_pass(), ["nothing to dispatch"])

    def test_seeded_pr_does_nothing(self):
        conn = db.connect(paths.db_path())
        conn.execute("UPDATE prs SET seeded = 1")
        conn.close()
        self.sync_green("abc123")
        self.assertEqual(self.run_pass(), ["nothing to dispatch"])

    def test_pr_from_a_fork_does_nothing(self):
        self.write_gh_fixture(
            "view_acme-app_1",
            {
                "state": "OPEN", "isDraft": True, "headRefName": "feature/x", "title": "t",
                "statusCheckRollup": _PASSING, "headRefOid": "abc123", "isCrossRepository": True,
            },
        )
        self.run_cli(["sync", "--source", "gh"], None, self.repo_dir)
        self.assertEqual(self.run_pass(), ["nothing to dispatch"])
        self.assertEqual(self.ready_calls(), [])

    def test_rule_absent_does_nothing(self):
        self.write_block({})
        self.sync_green("abc123")
        self.assertEqual(self.run_pass(), ["nothing to dispatch"])
