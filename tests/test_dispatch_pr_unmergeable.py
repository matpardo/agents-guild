import os

from guild import db, paths
from tests.test_dispatch_checks_failing import ChecksFailingBase
from tests.test_dispatch_checks_failing import _FAILING


class UnmergeableTests(ChecksFailingBase):
    def setUp(self):
        super().setUp()
        self.write_block({"pr_unmergeable": "on"})

    def sync_pr(self, head_sha, mergeable, threads, extra, state, is_draft):
        fixture = {
            "state": state, "isDraft": is_draft, "headRefName": "feature/x", "title": "t",
            "statusCheckRollup": [], "headRefOid": head_sha, "mergeable": mergeable,
        }
        if state == "MERGED":
            fixture["mergedAt"] = "2026-10-04T00:00:00Z"
        fixture.update(extra)
        self.write_gh_fixture("view_acme-app_1", fixture)
        self.write_gh_fixture(
            "threads_acme-app_1",
            {"data": {"repository": {"pullRequest": {"reviewThreads": {
                "nodes": [{"isResolved": False}] * threads}}}}},
        )
        code, out, err = self.run_cli(["sync", "--source", "gh"], None, self.repo_dir)
        self.assertEqual(code, 0, err)

    def sync_bad(self, head_sha, mergeable, threads):
        self.sync_pr(head_sha, mergeable, threads, {}, "OPEN", True)

    def test_unresolved_threads_launch_the_owner_once_per_head_and_slug_set(self):
        self.sync_bad("abc123", "MERGEABLE", 3)
        lines = self.run_pass()
        self.assertEqual(
            lines, ["acme: pr_unmergeable acme/app#1 -> launched alpha g2 (window @10, mode acceptEdits)"]
        )
        self.assertEqual(self.decision_keys(), ["pr_unmergeable:acme/app#1:abc123:unresolved_threads"])
        command = self.tmux.launch_calls()[0][-1]
        self.assertTrue(
            command.endswith(
                "'Continue the work described in the guild brief. Dispatched: acme/app#1 is not mergeable"
                " (unresolved threads); run gh pr view 1 --repo acme/app and resolve review threads.'"
            )
        )

    def test_thread_count_change_does_not_retrigger(self):
        self.write_block({"pr_unmergeable": "dry-run"})
        self.sync_bad("abc123", "MERGEABLE", 3)
        self.run_pass()
        self.sync_bad("abc123", "MERGEABLE", 4)
        self.assertEqual(self.run_pass(), ["nothing to dispatch"])

    def test_new_head_retriggers(self):
        self.write_block({"pr_unmergeable": "dry-run"})
        self.sync_bad("abc123", "MERGEABLE", 3)
        self.run_pass()
        self.sync_bad("def456", "MERGEABLE", 3)
        self.assertEqual(len(self.run_pass()), 1)

    def test_added_slug_retriggers(self):
        self.write_block({"pr_unmergeable": "dry-run"})
        self.sync_bad("abc123", "MERGEABLE", 3)
        self.run_pass()
        self.sync_bad("abc123", "CONFLICTING", 3)
        self.assertEqual(len(self.run_pass()), 1)
        self.assertEqual(
            self.decision_keys(),
            [
                "pr_unmergeable:acme/app#1:abc123:conflict,unresolved_threads",
                "pr_unmergeable:acme/app#1:abc123:unresolved_threads",
            ],
        )

    def test_carried_forward_fields_are_read_from_the_row(self):
        self.sync_pr("abc123", "MERGEABLE", 0, {"reviewDecision": "CHANGES_REQUESTED"}, "OPEN", True)
        self.run_pass()
        self.sync_pr("def456", "MERGEABLE", 0, {"reviewDecision": "CHANGES_REQUESTED"}, "OPEN", True)
        self.assertEqual(self.decision_keys(), ["pr_unmergeable:acme/app#1:abc123:changes_requested"])

    def test_merged_pr_launches_nothing(self):
        self.sync_pr("abc123", "CONFLICTING", 3, {}, "MERGED", False)
        self.assertEqual(self.run_pass(), ["nothing to dispatch"])

    def test_seeded_pr_launches_nothing(self):
        conn = db.connect(paths.db_path())
        conn.execute("UPDATE prs SET seeded = 1")
        conn.close()
        self.sync_bad("abc123", "CONFLICTING", 3)
        self.assertEqual(self.run_pass(), ["nothing to dispatch"])

    def test_pr_from_a_fork_launches_nothing(self):
        self.sync_pr("abc123", "CONFLICTING", 3, {"isCrossRepository": True}, "OPEN", True)
        self.assertEqual(self.run_pass(), ["nothing to dispatch"])

    def test_clean_pr_launches_nothing(self):
        self.sync_bad("abc123", "MERGEABLE", 0)
        self.assertEqual(self.run_pass(), ["nothing to dispatch"])

    def test_failing_checks_alone_are_not_a_reason(self):
        self.sync_pr("abc123", "MERGEABLE", 0, {"statusCheckRollup": _FAILING}, "OPEN", True)
        self.assertEqual(self.run_pass(), ["nothing to dispatch"])

    def test_deferred_trigger_launches_once_the_session_ends(self):
        self.write_session(os.getpid(), "sess-1", "alpha")
        self.sync_bad("abc123", "MERGEABLE", 3)
        self.assertEqual(self.run_pass(), ["acme: pr_unmergeable acme/app#1 -> deferred alpha: live session"])
        (self.sessions_dir / "{}.json".format(os.getpid())).unlink()
        self.assertEqual(len(self.run_pass()), 1)

    def test_deferred_trigger_is_dropped_when_the_cause_resolved(self):
        self.write_session(os.getpid(), "sess-1", "alpha")
        self.sync_bad("abc123", "MERGEABLE", 3)
        self.run_pass()
        self.sync_bad("abc123", "MERGEABLE", 0)
        (self.sessions_dir / "{}.json".format(os.getpid())).unlink()
        self.assertEqual(self.run_pass(), ["nothing to dispatch"])
        self.assertEqual(self.tmux.launch_calls(), [])
