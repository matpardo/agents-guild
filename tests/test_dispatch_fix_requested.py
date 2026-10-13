import os

from tests.test_dispatch_checks_failing import ChecksFailingBase
from tests.test_dispatch_checks_failing import _FAILING


class FixRequestedTests(ChecksFailingBase):
    def setUp(self):
        super().setUp()
        self.write_block({"fix_requested": "on"})

    def ask_fix(self):
        code, out, err = self.run_cli(["pr", "ask-fix", "acme/app#1"], None, self.repo_dir)
        self.assertEqual(code, 0, err)

    def test_request_suggests_a_revive_to_the_owner(self):
        self.sync_open(_FAILING, "abc123")
        self.ask_fix()
        lines = self.run_pass()
        self.assertEqual(
            lines, ["acme: fix_requested acme/app#1 -> suggested revive alpha g2"]
        )
        self.assertRegex(self.decision_keys()[0], r"^fix_requested:acme/app#1:[0-9a-f-]{36}$")
        self.assertEqual(self.tmux.launch_calls(), [])

    def test_live_session_defers_until_it_ends(self):
        self.write_session(os.getpid(), "sess-1", "alpha")
        self.sync_open(_FAILING, "abc123")
        self.ask_fix()
        self.assertEqual(self.run_pass(), ["acme: fix_requested acme/app#1 -> deferred alpha: live session"])
        (self.sessions_dir / "{}.json".format(os.getpid())).unlink()
        self.assertEqual(
            self.run_pass(), ["acme: fix_requested acme/app#1 -> suggested revive alpha g2"]
        )

    def test_fires_once_per_request(self):
        self.write_block({"fix_requested": "dry-run"})
        self.sync_open(_FAILING, "abc123")
        self.ask_fix()
        self.assertEqual(len(self.run_pass()), 1)
        self.sync_open(_FAILING, "def456")
        self.assertEqual(self.run_pass(), ["nothing to dispatch"])
        code, out, err = self.run_cli(["pr", "ask-fix", "acme/app#1"], None, self.repo_dir)
        self.assertEqual(code, 1)
        self.assertEqual(len(self.decision_keys()), 1)

    def test_rule_absent_still_posts_the_notice_and_launches_nothing(self):
        self.write_block({"ask_answered": "on"})
        self.sync_open(_FAILING, "abc123")
        self.ask_fix()
        self.assertEqual(self.run_pass(), ["nothing to dispatch"])
        self.assertEqual(self.tmux.launch_calls(), [])
