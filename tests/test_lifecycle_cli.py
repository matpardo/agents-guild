import fcntl
import json
import subprocess
from unittest import mock

from guild import paths
from tests.lifecycle_fixtures import (
    FakeRunner,
    LifecycleFixture,
    failed_result,
    init_clone,
    ok_result,
    timeout_result,
)


class LifecycleRunCliTests(LifecycleFixture):
    def _run(self, argv, runner):
        with mock.patch("guild.lifecycle.run_process", runner):
            return self.run_cli(["lifecycle", "run"] + argv, "sess-1", self.repo_dir)

    def test_dry_run_prints_and_records_nothing(self):
        runner = FakeRunner([])
        code, out, err = self._run(["on_pr_merged", "--dry-run"], runner)
        self.assertEqual(code, 0, err)
        self.assertEqual(
            out.strip(),
            "would run: scripts/cleanup-merged.sh --dry-run (cwd {}, timeout 30m)".format(self.repo_dir),
        )
        self.assertEqual(runner.calls, [])
        self.assertEqual(self.ran_payloads(), [])

    def test_real_run_prints_ok_and_records_manual_trigger(self):
        runner = FakeRunner([ok_result()])
        code, out, err = self._run(["on_pr_merged"], runner)
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "lifecycle on_pr_merged: ok (exit 0, 0.0s)")
        self.assertEqual(self.ran_payloads()[0]["triggers"], ["manual"])
        self.assertEqual(len(runner.calls), 1)

    def test_failed_run_exits_one_and_posts_notice(self):
        code, out, err = self._run(["on_pr_merged"], FakeRunner([failed_result()]))
        self.assertEqual(code, 1)
        self.assertIn("lifecycle on_pr_merged: failed (exit 1, 0.0s)", err)
        self.assertEqual(len(self.notice_texts()), 1)

    def test_timeout_exits_one(self):
        code, out, err = self._run(["on_pr_closed"], FakeRunner([timeout_result()]))
        self.assertEqual(code, 1)
        self.assertIn("lifecycle on_pr_closed: timeout", err)

    def test_held_lock_prints_skipped_and_exits_zero(self):
        lock_dir = paths.ensure_private_dir(paths.state_dir() / "lifecycle")
        with open(lock_dir / "acme-on_pr_merged.lock", "a") as held:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            code, out, err = self._run(["on_pr_merged"], FakeRunner([]))
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "lifecycle on_pr_merged: skipped: locked")

    def test_unconfigured_event_is_an_error(self):
        self.set_lifecycle(["on_pr_closed"])
        code, out, err = self._run(["on_pr_merged"], FakeRunner([]))
        self.assertEqual(code, 1)
        self.assertIn("project 'acme' has no lifecycle.on_pr_merged configured", err)

    def test_several_clones_without_repo_is_an_error(self):
        data = self.project()
        data["github"]["repos"] = ["acme/app", "acme/web"]
        self.config_file().write_text(json.dumps(data))
        init_clone(self.repo_dir.parent / "web", "acme/web")
        code, out, err = self._run(["on_pr_merged"], FakeRunner([]))
        self.assertEqual(code, 1)
        self.assertIn("pass --repo", err)

    def test_repo_flag_picks_the_clone(self):
        data = self.project()
        data["github"]["repos"] = ["acme/app", "acme/web"]
        self.config_file().write_text(json.dumps(data))
        init_clone(self.repo_dir.parent / "web", "acme/web")
        runner = FakeRunner([ok_result()])
        code, out, err = self._run(["on_pr_merged", "--repo", "acme/web"], runner)
        self.assertEqual(code, 0, err)
        self.assertEqual(runner.calls[0]["cwd"], str(self.repo_dir.parent / "web"))

    def test_no_clone_is_an_error(self):
        subprocess.run(
            ["git", "-C", str(self.repo_dir), "remote", "set-url", "origin", "https://github.com/other/thing"],
            check=True,
        )
        code, out, err = self._run(["on_pr_merged"], FakeRunner([]))
        self.assertEqual(code, 1)
        self.assertIn("no local clone", err)
