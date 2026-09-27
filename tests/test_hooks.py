import time
from unittest import mock

from tests.testutil import GuildTestCase


class SessionStartHookTests(GuildTestCase):
    def test_unbound_prints_hint(self):
        code, out, err = self.run_hook("session-start", {"session_id": "sess-1", "cwd": str(self.root)})
        self.assertEqual(code, 0)
        self.assertIn("session not bound", out)

    def test_bound_prints_brief_and_spawns_sync(self):
        repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha"], "sess-1", repo_dir)
        code, out, err = self.run_hook("session-start", {"session_id": "sess-1", "cwd": str(repo_dir)})
        self.assertEqual(code, 0)
        self.assertIn("party: alpha", out)


class PromptSubmitHookTests(GuildTestCase):
    def test_unbound_hint_shown_once(self):
        payload = {"session_id": "sess-1", "cwd": str(self.root)}
        code, out, err = self.run_hook("prompt-submit", payload)
        self.assertIn("session not bound", out)
        code, out, err = self.run_hook("prompt-submit", payload)
        self.assertEqual(out, "")

    def test_bound_reports_new_notice(self):
        repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha"], "sess-1", repo_dir)
        self.run_cli(["party", "start", "beta"], "sess-2", repo_dir)
        self.run_cli(["notice", "create", "pipeline down", "--to", "guild", "--ttl", "2h"], None, None)
        code, out, err = self.run_hook("prompt-submit", {"session_id": "sess-2", "cwd": str(repo_dir)})
        self.assertIn("pipeline down", out)

    def test_latency_under_100ms(self):
        repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha"], "sess-1", repo_dir)
        payload = {"session_id": "sess-1", "cwd": str(repo_dir)}
        started = time.monotonic()
        self.run_hook("prompt-submit", payload)
        elapsed_ms = (time.monotonic() - started) * 1000
        self.assertLess(elapsed_ms, 100, "prompt-submit hook took {:.1f}ms".format(elapsed_ms))


class HookErrorContainmentTests(GuildTestCase):
    def test_session_start_swallows_exceptions(self):
        with mock.patch(
            "guild.commands.hook.session_start", side_effect=RuntimeError("boom")
        ):
            code, out, err = self.run_hook("session-start", {"session_id": "sess-1", "cwd": str(self.root)})
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "guild hook error: boom")

    def test_prompt_submit_swallows_exceptions(self):
        with mock.patch(
            "guild.commands.hook.prompt_submit", side_effect=RuntimeError("boom")
        ):
            code, out, err = self.run_hook("prompt-submit", {"session_id": "sess-1", "cwd": str(self.root)})
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "guild hook error: boom")

    def test_pre_push_swallows_exceptions_as_system_message(self):
        with mock.patch("guild.commands.hook.pre_push", side_effect=RuntimeError("boom")):
            code, out, err = self.run_hook(
                "pre-push", {"tool_input": {"command": "git push"}, "cwd": str(self.root)}
            )
        self.assertEqual(code, 0)
        self.assertIn("guild hook error: boom", out)


class PrePushHookTests(GuildTestCase):
    def _init_repo(self, name, branch):
        import subprocess

        repo_dir = self.root / name
        repo_dir.mkdir(parents=True)
        subprocess.run(["git", "init", "-q"], cwd=str(repo_dir), check=True)
        subprocess.run(["git", "checkout", "-q", "-b", branch], cwd=str(repo_dir), check=True)
        return repo_dir

    def test_non_push_command_allowed_without_network(self):
        code, out, err = self.run_hook(
            "pre-push", {"tool_input": {"command": "ls -la"}, "cwd": str(self.root)}
        )
        self.assertEqual(code, 0)
        self.assertEqual(out, "")

    def test_push_allowed_when_pr_open(self):
        repo_dir = self._init_repo("repo1", "feature/open")
        self.write_gh_fixture("list_feature-open", [{"number": 1, "state": "OPEN", "url": "x"}])
        code, out, err = self.run_hook(
            "pre-push",
            {"tool_input": {"command": "git push origin feature/open"}, "cwd": str(repo_dir)},
        )
        self.assertEqual(code, 0)

    def test_push_blocked_when_only_merged_pr(self):
        repo_dir = self._init_repo("repo2", "feature/merged")
        self.write_gh_fixture("list_feature-merged", [{"number": 2, "state": "MERGED", "url": "x"}])
        code, out, err = self.run_hook(
            "pre-push",
            {"tool_input": {"command": "git push origin feature/merged"}, "cwd": str(repo_dir)},
        )
        self.assertEqual(code, 2)
        self.assertIn("belongs to merged/closed PR #2", err)

    def test_push_allowed_when_no_prs(self):
        repo_dir = self._init_repo("repo3", "feature/fresh")
        self.write_gh_fixture("list_feature-fresh", [])
        code, out, err = self.run_hook(
            "pre-push",
            {"tool_input": {"command": "git push origin feature/fresh"}, "cwd": str(repo_dir)},
        )
        self.assertEqual(code, 0)

    def test_gh_failure_does_not_block(self):
        repo_dir = self._init_repo("repo4", "feature/unknown")
        self.write_gh_error("list_feature-unknown", "network down")
        code, out, err = self.run_hook(
            "pre-push",
            {"tool_input": {"command": "git push origin feature/unknown"}, "cwd": str(repo_dir)},
        )
        self.assertEqual(code, 0)
        self.assertIn("systemMessage", out)
        self.assertIn("could not verify PR state", out)

    def test_chained_command_with_push(self):
        repo_dir = self._init_repo("repo5", "feature/chained")
        self.write_gh_fixture("list_feature-chained", [{"number": 3, "state": "MERGED", "url": "x"}])
        code, out, err = self.run_hook(
            "pre-push",
            {
                "tool_input": {"command": "npm test && git push origin feature/chained"},
                "cwd": str(repo_dir),
            },
        )
        self.assertEqual(code, 2)

    def test_git_dash_c_dir_form(self):
        repo_dir = self._init_repo("repo6", "feature/dashc")
        self.write_gh_fixture("list_feature-dashc", [{"number": 4, "state": "CLOSED", "url": "x"}])
        code, out, err = self.run_hook(
            "pre-push",
            {
                "tool_input": {"command": "git -C {} push origin feature/dashc".format(repo_dir)},
                "cwd": str(self.root),
            },
        )
        self.assertEqual(code, 2)


if __name__ == "__main__":
    import unittest

    unittest.main()
