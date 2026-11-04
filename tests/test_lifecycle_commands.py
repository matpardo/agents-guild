import fcntl
import json
from unittest import mock

from guild import paths
from guild.commands import lifecycle as lifecycle_commands
from tests.lifecycle_fixtures import (
    ARGV,
    TIMEOUT_MINUTES,
    FakeRunner,
    LifecycleFixture,
    error_result,
    exit_result,
    failed_result,
    ok_result,
    timeout_result,
)


class RunGroupTests(LifecycleFixture):
    def _run(self, runner, event="on_pr_merged", repo="acme/app", refs=("acme/app#12",)):
        return lifecycle_commands.run_group(self.ctx, self.project(), event, repo, list(refs), runner)

    def _lock_path(self, event="on_pr_merged"):
        return paths.state_dir() / "lifecycle" / "acme-{}.lock".format(event)

    def test_ok_records_payload_without_notice(self):
        runner = FakeRunner([ok_result()])
        self._run(runner)
        self.assertEqual(
            runner.calls,
            [{"argv": ARGV, "cwd": str(self.repo_dir), "timeout_seconds": TIMEOUT_MINUTES * 60}],
        )
        self.assertEqual(
            self.ran_payloads(),
            [
                {
                    "project": "acme",
                    "event": "on_pr_merged",
                    "repo": "acme/app",
                    "triggers": ["acme/app#12"],
                    "argv": ARGV,
                    "cwd": str(self.repo_dir),
                    "status": "ok",
                    "exit_code": 0,
                    "duration_ms": 12,
                    "output_tail": "cleaned",
                    "reason": None,
                }
            ],
        )
        self.assertEqual(self.notice_texts(), [])

    def test_failed_records_status_and_posts_notice(self):
        self._run(FakeRunner([failed_result()]))
        payload = self.ran_payloads()[0]
        self.assertEqual((payload["status"], payload["exit_code"]), ("failed", 1))
        self.assertEqual(self.notice_texts(), ["lifecycle on_pr_merged failed for acme (exit 1): see guild history"])

    def test_listed_exit_code_counts_as_ok_without_notice(self):
        self.set_ok_exit_codes("on_pr_merged", [5])
        self._run(FakeRunner([exit_result(5)]))
        payload = self.ran_payloads()[0]
        self.assertEqual((payload["status"], payload["exit_code"]), ("ok", 5))
        self.assertEqual(self.notice_texts(), [])

    def test_unlisted_exit_code_still_fails_with_ok_exit_codes_declared(self):
        self.set_ok_exit_codes("on_pr_merged", [5])
        self._run(FakeRunner([exit_result(6)]))
        payload = self.ran_payloads()[0]
        self.assertEqual((payload["status"], payload["exit_code"]), ("failed", 6))
        self.assertEqual(self.notice_texts(), ["lifecycle on_pr_merged failed for acme (exit 6): see guild history"])

    def test_timeout_records_status_and_posts_notice(self):
        self._run(FakeRunner([timeout_result()]))
        self.assertEqual(self.ran_payloads()[0]["status"], "timeout")
        self.assertEqual(self.notice_texts(), ["lifecycle on_pr_merged failed for acme (timeout): see guild history"])

    def test_launch_error_records_reason_and_posts_notice(self):
        self._run(FakeRunner([error_result()]))
        payload = self.ran_payloads()[0]
        self.assertEqual((payload["status"], payload["reason"]), ("error", "permission denied"))
        self.assertIsNone(payload["exit_code"])
        self.assertEqual(self.notice_texts(), ["lifecycle on_pr_merged failed for acme (error): see guild history"])

    def test_notice_never_carries_output_or_argv(self):
        self._run(FakeRunner([failed_result()]))
        text = self.notice_texts()[0]
        self.assertNotIn("secret-output", text)
        self.assertNotIn("cleanup-merged", text)

    def test_same_first_trigger_twice_posts_one_notice(self):
        self._run(FakeRunner([failed_result(), failed_result()]))
        self._run(FakeRunner([failed_result()]))
        self.assertEqual(len(self.ran_payloads()), 2)
        self.assertEqual(len(self.notice_texts()), 1)

    def test_missing_checkout_is_an_error_and_never_runs(self):
        runner = FakeRunner([])
        self._run(runner, repo="acme/other")
        self.assertEqual(runner.calls, [])
        payload = self.ran_payloads()[0]
        self.assertEqual((payload["status"], payload["reason"]), ("error", "no checkout"))
        self.assertIsNone(payload["cwd"])
        self.assertEqual(len(self.notice_texts()), 1)

    def test_held_lock_skips_without_runner_or_notice(self):
        lock_dir = paths.ensure_private_dir(paths.state_dir() / "lifecycle")
        with open(lock_dir / "acme-on_pr_merged.lock", "a") as held:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            runner = FakeRunner([])
            self._run(runner)
        self.assertEqual(runner.calls, [])
        payload = self.ran_payloads()[0]
        self.assertEqual((payload["status"], payload["reason"]), ("skipped", "locked"))
        self.assertIsNone(payload["exit_code"])
        self.assertEqual(self.notice_texts(), [])

    def test_lock_for_other_event_does_not_block(self):
        lock_dir = paths.ensure_private_dir(paths.state_dir() / "lifecycle")
        with open(lock_dir / "acme-on_pr_closed.lock", "a") as held:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            runner = FakeRunner([ok_result()])
            self._run(runner)
        self.assertEqual(len(runner.calls), 1)

    def _assert_lock_free(self):
        with open(self._lock_path(), "a") as probe:
            fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def test_lock_released_after_run(self):
        self._run(FakeRunner([ok_result()]))
        self._assert_lock_free()

    def test_lock_released_after_runner_exception(self):
        def exploding(argv, cwd, timeout_seconds):
            raise RuntimeError("boom")

        with self.assertRaises(RuntimeError):
            self._run(exploding)
        self._assert_lock_free()


class RunSyncTriggersTests(LifecycleFixture):
    def _run(self, triggers, runner):
        lifecycle_commands.run_sync_triggers(self.ctx, [self.project()], triggers, runner)

    def test_two_merges_in_one_pass_run_once(self):
        runner = FakeRunner([ok_result()])
        self._run([("on_pr_merged", "acme/app", 2), ("on_pr_merged", "acme/app", 1)], runner)
        self.assertEqual(len(runner.calls), 1)
        self.assertEqual(self.ran_payloads()[0]["triggers"], ["acme/app#1", "acme/app#2"])

    def test_merge_and_close_run_separately(self):
        runner = FakeRunner([ok_result(), ok_result()])
        self._run([("on_pr_merged", "acme/app", 1), ("on_pr_closed", "acme/app", 2)], runner)
        self.assertEqual(len(runner.calls), 2)
        self.assertEqual(sorted(payload["event"] for payload in self.ran_payloads()), ["on_pr_closed", "on_pr_merged"])

    def test_unconfigured_event_is_not_run(self):
        self.set_lifecycle(["on_pr_closed"])
        runner = FakeRunner([])
        self._run([("on_pr_merged", "acme/app", 1)], runner)
        self.assertEqual(runner.calls, [])
        self.assertEqual(self.ran_payloads(), [])

    def test_repo_of_no_project_is_ignored(self):
        runner = FakeRunner([])
        self._run([("on_pr_merged", "other/thing", 1)], runner)
        self.assertEqual(runner.calls, [])

    def test_payload_survives_json_round_trip(self):
        self._run([("on_pr_merged", "acme/app", 1)], FakeRunner([ok_result()]))
        json.dumps(self.ran_payloads())

    def test_raising_runner_is_recorded_and_next_group_still_runs(self):
        calls = []

        def runner(argv, cwd, timeout_seconds):
            calls.append(argv)
            if len(calls) == 1:
                raise RuntimeError("boom")
            return ok_result()

        self._run([("on_pr_closed", "acme/app", 2), ("on_pr_merged", "acme/app", 1)], runner)
        self.assertEqual(len(calls), 2)
        payloads = {payload["event"]: payload for payload in self.ran_payloads()}
        self.assertEqual(payloads["on_pr_closed"]["status"], "error")
        self.assertEqual(payloads["on_pr_closed"]["reason"], "RuntimeError: boom")
        self.assertEqual(payloads["on_pr_merged"]["status"], "ok")
        self.assertEqual(self.notice_texts(), ["lifecycle on_pr_closed failed for acme (error): see guild history"])

    def test_lock_failure_is_recorded_as_error(self):
        with mock.patch("guild.locking.paths.ensure_private_dir", side_effect=OSError("disk full")):
            self._run([("on_pr_merged", "acme/app", 1)], FakeRunner([]))
        payload = self.ran_payloads()[0]
        self.assertEqual((payload["status"], payload["reason"]), ("error", "OSError: disk full"))
        self.assertEqual(len(self.notice_texts()), 1)
