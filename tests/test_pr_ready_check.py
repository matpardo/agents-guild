from tests.mq_fixtures import OPEN_VIEW, TASKS_MD, MergeQueueTestCase


class ReadyCheckTests(MergeQueueTestCase):
    def setUp(self):
        super().setUp()
        self.start_party("alpha", "sess-1")
        code, out, err = self.sync_sdd(self.repo_dir, "sess-1", "acme", "demo-epic", TASKS_MD)
        self.assertEqual(code, 0, err)
        self.add_quest("sess-1", "qa", "demo-epic", "T01,T02,T03")

    def check(self, number):
        return self.run_cli(["pr", "ready-check", "acme/app#{}".format(number)], "sess-1", self.repo_dir)

    def test_ready_pr_exits_zero(self):
        self.track("sess-1", 3, "qa/T03", "ready")
        self.sync_gh("sess-1")
        code, out, err = self.check(3)
        self.assertEqual((code, out), (0, "acme/app#3 ready\n"))

    def test_lists_every_blocker(self):
        self.track("sess-1", 3, "qa/T03", "ready")
        self.write_gh_fixture("view_acme-app_3", dict(
            OPEN_VIEW, mergeable="CONFLICTING", statusCheckRollup=[{"conclusion": "FAILURE"}]
        ))
        self.sync_gh("sess-1")
        self.run_cli(["pr", "set", "acme/app#3", "--needs-ask-answer"], "sess-1", self.repo_dir)
        code, out, err = self.check(3)
        self.assertEqual(code, 1)
        self.assertEqual(
            out.splitlines(),
            ["acme/app#3 blocked", "- needs ask answer", "- checks failing (1)", "- merge conflict"],
        )

    def test_shows_wait_on_predecessor(self):
        self.track("sess-1", 1, "qa/T01", "ready")
        self.track("sess-1", 2, "qa/T02", "draft")
        self.sync_gh("sess-1")
        code, out, err = self.check(1)
        self.assertEqual(code, 1)
        self.assertEqual(out.splitlines(), ["acme/app#1 blocked", "- waits on task T02", "- wait: waits on acme/app#2"])

    def test_draft_gate_hints_promote_command(self):
        self.track("sess-1", 3, "qa/T03", "draft")
        code, out, err = self.check(3)
        self.assertEqual(code, 1)
        self.assertIn("- gate: draft (gh pr ready 3)", out.splitlines())

    def test_untracked_pr_errors(self):
        code, out, err = self.check(9)
        self.assertEqual(code, 1)
        self.assertIn("not tracked", err)


class ExternalReadyCheckTests(ReadyCheckTests):
    def test_external_block_fails_the_check_and_lists_the_reason(self):
        self.track("sess-1", 3, "qa/T03", "ready")
        self.sync_gh("sess-1")
        code, out, err = self.run_cli(
            ["pr", "set", "acme/app#3", "--blocked-external", "team meeting"], "sess-1", self.repo_dir
        )
        self.assertEqual(code, 0, err)
        code, out, err = self.check(3)
        self.assertEqual((code, out.splitlines()), (1, ["acme/app#3 blocked", "- external: team meeting"]))
