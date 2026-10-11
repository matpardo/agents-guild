import subprocess

from tests.mq_fixtures import OPEN_VIEW, MergeQueueTestCase


class AskFlagTests(MergeQueueTestCase):
    def setUp(self):
        super().setUp()
        self.start_party("alpha", "sess-1")
        self.run_cli(["quest", "add", "qa", "--title", "qa", "--no-epic"], "sess-1", self.repo_dir)
        self.run_cli(["task", "add", "qa/T01", "--title", "t"], "sess-1", self.repo_dir)
        self.track("sess-1", 1, "qa/T01", "ready")
        self.assertEqual(self.sync_gh("sess-1")[0], 0)

    def ask(self, ref):
        code, out, err = self.run_cli(
            ["ask", "ok?", "--context", "x", "--ref", ref], "sess-1", self.repo_dir
        )
        self.assertEqual(code, 0, err)

    def queue_out(self):
        return self.run_cli(["merge-queue", "--party", "alpha"], None, self.repo_dir)[1]

    def ready_check(self):
        return self.run_cli(["pr", "ready-check", "acme/app#1"], None, self.repo_dir)

    def test_open_ask_blocks_the_pr_naming_the_ask(self):
        self.ask("pr:acme/app#1")
        self.assertIn("needs ask answer (ask #1)", self.queue_out())
        code, out, err = self.ready_check()
        self.assertEqual(code, 1)
        self.assertIn("needs ask answer (ask #1)", out)

    def test_answer_unblocks_without_pr_set(self):
        self.ask("pr:acme/app#1")
        self.run_cli(["answer", "1", "go"], None, None)
        self.assertNotIn("needs ask answer", self.queue_out())

    def test_dismiss_unblocks_without_pr_set(self):
        self.ask("pr:acme/app#1")
        self.run_cli(["dismiss", "1"], None, None)
        self.assertNotIn("needs ask answer", self.queue_out())

    def test_ask_on_another_pr_does_not_block(self):
        self.ask("task:qa/T01")
        self.assertNotIn("needs ask answer", self.queue_out())

    def test_manual_flag_blocks_without_an_ask(self):
        self.run_cli(["pr", "set", "acme/app#1", "--needs-ask-answer"], "sess-1", self.repo_dir)
        out = self.queue_out()
        self.assertIn("needs ask answer", out)
        self.assertNotIn("(ask #", out)

    def test_manual_off_does_not_hide_an_open_ask(self):
        self.run_cli(["pr", "set", "acme/app#1", "--needs-ask-answer"], "sess-1", self.repo_dir)
        self.ask("pr:acme/app#1")
        self.run_cli(["pr", "set", "acme/app#1", "--no-needs-ask-answer"], "sess-1", self.repo_dir)
        self.assertIn("needs ask answer (ask #1)", self.queue_out())
        self.run_cli(["answer", "1", "go"], None, None)
        self.assertNotIn("needs ask answer", self.queue_out())

    def test_board_shows_the_ask_source(self):
        self.ask("pr:acme/app#1")
        code, out, err = self.run_cli(["board"], None, self.repo_dir)
        self.assertEqual(code, 0, err)
        self.assertIn("needs-ask-answer (ask #1)", out)


class RedMainPushTests(MergeQueueTestCase):
    def setUp(self):
        super().setUp()
        for command in (
            ["git", "init", "-q", "-b", "main"],
            ["git", "config", "user.email", "t@t.com"],
            ["git", "config", "user.name", "t"],
            ["git", "commit", "--allow-empty", "-q", "-m", "init"],
            ["git", "update-ref", "refs/remotes/origin/main", "HEAD"],
            ["git", "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main"],
            ["git", "remote", "add", "origin", "https://github.com/acme/app.git"],
            ["git", "checkout", "-q", "-b", "feature/fix"],
        ):
            subprocess.run(command, cwd=str(self.repo_dir), check=True)
        self.start_party("alpha", "sess-1")
        self.run_cli(["quest", "add", "qa", "--title", "qa", "--no-epic"], "sess-1", self.repo_dir)
        self.run_cli(["task", "add", "qa/T01", "--title", "t"], "sess-1", self.repo_dir)
        self.write_gh_fixture("list_feature-fix", [])

    def push(self):
        return self.run_hook(
            "pre-push",
            {
                "session_id": "sess-1",
                "tool_input": {"command": "git push origin feature/fix"},
                "cwd": str(self.repo_dir),
            },
        )

    def mark_red(self):
        self.run_cli(["main", "red", "acme/app", "--reason", "lint broke"], None, self.repo_dir)

    def track_fixer(self, flag):
        self.write_gh_fixture("view_acme-app_9", dict(OPEN_VIEW, headRefName="feature/fix"))
        code, out, err = self.run_cli(
            ["pr", "track", "acme/app#9", "--task", "qa/T01", "--what", "fix", "--waits", "review"] + flag,
            "sess-1", self.repo_dir,
        )
        self.assertEqual(code, 0, err)

    def test_silent_without_main_status(self):
        code, out, err = self.push()
        self.assertEqual((code, out), (0, ""))

    def test_allowed_when_main_is_green(self):
        self.mark_red()
        self.run_cli(["main", "green", "acme/app"], None, self.repo_dir)
        code, out, err = self.push()
        self.assertEqual((code, out), (0, ""))

    def test_refused_while_main_is_red_with_reason_and_way_out(self):
        self.mark_red()
        code, out, err = self.push()
        self.assertEqual(code, 2)
        self.assertIn("main of acme/app is red: lint broke (manual, red since", err)
        self.assertIn("fix main first, or flag your PR with `guild pr set <ref> --fixes-main`", err)

    def test_refused_for_a_pr_not_flagged_fixes_main(self):
        self.mark_red()
        self.track_fixer([])
        self.assertEqual(self.push()[0], 2)

    def test_allowed_for_the_branch_of_a_fixes_main_pr(self):
        self.mark_red()
        self.track_fixer(["--fixes-main"])
        code, out, err = self.push()
        self.assertEqual((code, out), (0, ""))
