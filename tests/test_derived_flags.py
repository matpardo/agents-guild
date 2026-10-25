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
        code, out, err = self.run_cli(["ask", "ok?", "--context", "x", "--ref", ref], "sess-1", self.repo_dir)
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
    def init_repo(self, directory, branch):
        directory.mkdir(parents=True, exist_ok=True)
        for command in (
            ["git", "init", "-q", "-b", "main"],
            ["git", "config", "user.email", "t@t.com"],
            ["git", "config", "user.name", "t"],
            ["git", "commit", "--allow-empty", "-q", "-m", "init"],
            ["git", "update-ref", "refs/remotes/origin/main", "HEAD"],
            ["git", "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main"],
            ["git", "remote", "add", "origin", "https://github.com/acme/app.git"],
            ["git", "checkout", "-q", "-b", branch],
        ):
            subprocess.run(command, cwd=str(directory), check=True)

    def setUp(self):
        super().setUp()
        self.init_repo(self.repo_dir, "feature/fix")
        self.worktree = self.root / "wt"
        self.init_repo(self.worktree, "feature/wt")
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
            "sess-1",
            self.repo_dir,
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

    def test_billing_blocked_main_does_not_refuse_and_warns(self):
        self.mark_billing_blocked()
        code, out, err = self.push()
        self.assertEqual(code, 0, err)
        self.assertIn("main of acme/app is blocked by billing: CI will not run", out + err)

    def hook_command(self, command):
        return self.run_hook(
            "pre-push",
            {"session_id": "sess-1", "tool_input": {"command": command}, "cwd": str(self.repo_dir)},
        )

    def list_pr(self, is_draft):
        self.write_gh_fixture("list_feature-fix", [{"number": 9, "state": "OPEN", "url": "u", "isDraft": is_draft}])

    def test_no_pr_push_warns_while_main_is_red(self):
        self.mark_red()
        code, out, err = self.push()
        self.assertEqual(code, 0, err)
        self.assertIn("main of acme/app is red: lint broke (manual, red since", out)
        self.assertIn("keep iterating in draft, do not mark the PR Ready", out)

    def test_draft_pr_push_warns_while_main_is_red(self):
        self.mark_red()
        self.list_pr(True)
        code, out, err = self.push()
        self.assertEqual(code, 0, err)
        self.assertIn("keep iterating in draft", out)

    def test_ready_pr_push_is_refused_while_main_is_red(self):
        self.mark_red()
        self.list_pr(False)
        code, out, err = self.push()
        self.assertEqual(code, 2)
        self.assertIn("main of acme/app is red: lint broke (manual, red since", err)
        self.assertIn("gh pr ready --undo 9", err)
        self.assertIn("guild pr set <ref> --fixes-main", err)

    def test_ready_pr_push_allowed_for_a_fixes_main_pr(self):
        self.mark_red()
        self.list_pr(False)
        self.track_fixer(["--fixes-main"])
        code, out, err = self.push()
        self.assertEqual((code, out), (0, ""))

    def test_fixes_flaky_does_not_exempt_a_ready_pr_push(self):
        self.mark_red()
        self.list_pr(False)
        self.track_fixer(["--fixes-flaky"])
        self.assertEqual(self.push()[0], 2)

    def test_ready_pr_push_allowed_when_main_is_green(self):
        self.list_pr(False)
        code, out, err = self.push()
        self.assertEqual((code, out), (0, ""))

    def test_gh_pr_ready_refused_while_main_is_red(self):
        self.mark_red()
        code, out, err = self.hook_command("gh pr ready 12")
        self.assertEqual(code, 2)
        self.assertIn("main of acme/app is red: lint broke", err)
        self.assertIn("gh pr ready --undo", err)

    def test_gh_pr_ready_forms_refused_while_main_is_red(self):
        self.mark_red()
        for command in (
            "gh pr ready",
            "gh pr ready feature/fix",
            "gh pr ready https://github.com/acme/app/pull/12",
            "gh -R acme/app pr ready 12",
            "gh --repo acme/app pr ready 12",
            "gh pr ready 12 -R acme/app",
            "git status && gh pr ready 12",
            "true; gh pr ready 12",
        ):
            with self.subTest(command=command):
                self.assertEqual(self.hook_command(command)[0], 2)

    def test_gh_pr_ready_undo_passes_while_main_is_red(self):
        self.mark_red()
        code, out, err = self.hook_command("gh pr ready --undo 12")
        self.assertEqual((code, out), (0, ""))

    def test_gh_pr_create_needs_draft_while_main_is_red(self):
        self.mark_red()
        self.assertEqual(self.hook_command("gh pr create --title x")[0], 2)
        self.assertEqual(self.hook_command("gh pr create --draft")[0], 0)
        self.assertEqual(self.hook_command("gh pr create -d")[0], 0)

    def test_gh_pr_commands_pass_when_main_is_green(self):
        for command in ("gh pr ready 12", "gh pr create --title x", "gh -R acme/app pr ready 12"):
            with self.subTest(command=command):
                self.assertEqual(self.hook_command(command), (0, "", ""))

    def test_gh_pr_ready_passes_for_a_fixes_main_pr_number(self):
        self.mark_red()
        self.track_fixer(["--fixes-main"])
        self.assertEqual(self.hook_command("gh pr ready 9"), (0, "", ""))
        self.assertEqual(self.hook_command("gh pr ready 12")[0], 2)

    def test_gh_pr_ready_refused_for_a_fixes_flaky_pr_number(self):
        self.mark_red()
        self.track_fixer(["--fixes-flaky"])
        self.assertEqual(self.hook_command("gh pr ready 9")[0], 2)

    def test_billing_blocked_main_does_not_refuse_gh_pr_ready(self):
        self.mark_billing_blocked()
        self.assertEqual(self.hook_command("gh pr ready 12")[0], 0)

    def hook_command_from(self, cwd, command):
        return self.run_hook(
            "pre-push",
            {"session_id": "sess-1", "tool_input": {"command": command}, "cwd": str(cwd)},
        )

    def list_worktree_pr(self, is_draft):
        self.write_gh_fixture("list_feature-wt", [{"number": 9, "state": "OPEN", "url": "u", "isDraft": is_draft}])

    def test_cd_into_worktree_push_to_ready_pr_is_refused(self):
        self.mark_red()
        self.list_worktree_pr(False)
        code, out, err = self.hook_command_from(self.root, "cd {} && git push".format(self.worktree))
        self.assertEqual(code, 2)
        self.assertIn("pushing to Ready PR #9", err)

    def test_cd_into_worktree_push_to_draft_pr_warns(self):
        self.mark_red()
        self.list_worktree_pr(True)
        code, out, err = self.hook_command_from(self.root, "cd {} && git push".format(self.worktree))
        self.assertEqual(code, 0, err)
        self.assertIn("keep iterating in draft", out)

    def test_relative_cd_resolves_against_the_start_dir(self):
        self.mark_red()
        self.list_worktree_pr(False)
        self.assertEqual(self.hook_command_from(self.root, "cd wt && git push")[0], 2)

    def test_cd_inside_shell_c_is_followed(self):
        self.mark_red()
        self.list_worktree_pr(False)
        command = "bash -c 'cd {} && git push'".format(self.worktree)
        self.assertEqual(self.hook_command_from(self.root, command)[0], 2)

    def test_unresolvable_cd_makes_the_push_unresolved(self):
        self.mark_red()
        missing = self.root / "missing"
        for command in ("cd {} && git push".format(missing), "cd && git push", "cd - && git push"):
            with self.subTest(command=command):
                code, out, err = self.hook_command_from(self.repo_dir, command)
                self.assertEqual(code, 0, err)
                self.assertIn("could not determine", out)

    def test_cd_into_worktree_gh_pr_ready_uses_the_worktree_repo(self):
        self.mark_red()
        self.assertEqual(self.hook_command_from(self.root, "cd {} && gh pr ready".format(self.worktree))[0], 2)

    def test_unresolvable_cd_makes_gh_pr_ready_unresolved(self):
        self.mark_red()
        code, out, err = self.hook_command_from(self.repo_dir, "cd {} && gh pr ready".format(self.root / "missing"))
        self.assertEqual(code, 0, err)
        self.assertIn("could not determine", out)

    def test_gh_repo_equals_forms_refused_while_main_is_red(self):
        self.mark_red()
        for command in (
            "gh pr ready 12 --repo=acme/app",
            "gh --repo=acme/app pr ready 12",
            "gh pr create --repo=acme/app --title=x",
        ):
            with self.subTest(command=command):
                self.assertEqual(self.hook_command_from(self.root, command)[0], 2)

    def test_gh_pr_create_head_equals_form_exempts_a_fixes_main_branch(self):
        self.mark_red()
        self.track_fixer(["--fixes-main"])
        self.assertEqual(self.hook_command("gh pr create --head=feature/fix")[0], 0)
        self.assertEqual(self.hook_command("gh pr create --head=feature/other")[0], 2)

    def test_gh_pr_create_bundled_draft_flags(self):
        self.mark_red()
        self.assertEqual(self.hook_command("gh pr create -fd")[0], 0)
        self.assertEqual(self.hook_command("gh pr create -df")[0], 0)
        self.assertEqual(self.hook_command("gh pr create -f")[0], 2)
