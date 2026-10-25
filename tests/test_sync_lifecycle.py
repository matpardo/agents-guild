import json
from unittest import mock

from guild.commands import sync as sync_commands
from tests.lifecycle_fixtures import (
    FakeRunner,
    LifecycleFixture,
    failed_result,
    ok_result,
)

_OPEN_DRAFT = {"state": "OPEN", "isDraft": True, "headRefName": "feature/x", "title": "t"}
_MERGED = {
    "state": "MERGED",
    "isDraft": False,
    "headRefName": "feature/x",
    "title": "t",
    "mergedAt": "2026-01-01T00:00:00Z",
    "statusCheckRollup": [],
}
_CLOSED = {"state": "CLOSED", "isDraft": False, "headRefName": "feature/x", "title": "t", "statusCheckRollup": []}


class SyncLifecycleTests(LifecycleFixture):
    def setUp(self):
        super().setUp()
        self.run_cli(["party", "start", "alpha", "--reason", "test reason"], "sess-1", self.repo_dir)
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", self.repo_dir)
        self.run_cli(["task", "add", "demo/T01", "--title", "First"], "sess-1", self.repo_dir)

    def _track(self, number, view):
        self.write_gh_fixture("view_acme-app_{}".format(number), view)
        code, out, err = self.run_cli(
            ["pr", "track", "acme/app#{}".format(number), "--task", "demo/T01", "--what", "x", "--waits", "y"],
            "sess-1",
            self.repo_dir,
        )
        self.assertEqual(code, 0, err)

    def _set_view(self, number, view):
        self.write_gh_fixture("view_acme-app_{}".format(number), view)

    def _sync(self, runner):
        with mock.patch("guild.lifecycle.run_process", runner):
            return self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)

    def test_draft_to_merged_fires_on_pr_merged_once(self):
        self._track(1, _OPEN_DRAFT)
        self._set_view(1, _MERGED)
        runner = FakeRunner([ok_result()])
        code, out, err = self._sync(runner)
        self.assertEqual(code, 0, err)
        self.assertEqual(len(runner.calls), 1)
        payload = self.ran_payloads()[0]
        self.assertEqual((payload["event"], payload["triggers"]), ("on_pr_merged", ["acme/app#1"]))
        self.assertEqual(payload["cwd"], str(self.repo_dir))

    def test_draft_to_closed_fires_on_pr_closed(self):
        self._track(1, _OPEN_DRAFT)
        self._set_view(1, _CLOSED)
        runner = FakeRunner([ok_result()])
        self._sync(runner)
        self.assertEqual([p["event"] for p in self.ran_payloads()], ["on_pr_closed"])

    def test_pr_already_merged_when_tracked_does_not_fire(self):
        self._track(1, _MERGED)
        runner = FakeRunner([])
        self._sync(runner)
        self.assertEqual(runner.calls, [])

    def test_pr_merged_on_github_before_tracking_does_not_fire_on_next_sync(self):
        self._track(1, _MERGED)
        runner = FakeRunner([])
        code, out, err = self._sync(runner)
        self.assertEqual(code, 0, err)
        self.assertEqual(runner.calls, [])
        self.assertEqual(self.ran_payloads(), [])

    def test_pr_already_closed_when_tracked_does_not_fire(self):
        self._track(1, _CLOSED)
        runner = FakeRunner([])
        self._sync(runner)
        self.assertEqual(runner.calls, [])

    def test_seeded_pr_does_not_fire(self):
        self._track(1, _OPEN_DRAFT)
        self.ctx.conn.execute("UPDATE prs SET seeded = 1, gh_state = NULL")
        self.ctx.conn.commit()
        self._set_view(1, _MERGED)
        runner = FakeRunner([])
        code, out, err = self._sync(runner)
        self.assertEqual(code, 0, err)
        self.assertEqual(runner.calls, [])

    def test_second_sync_does_not_refire(self):
        self._track(1, _OPEN_DRAFT)
        self._set_view(1, _MERGED)
        runner = FakeRunner([ok_result()])
        self._sync(runner)
        self._sync(runner)
        self.assertEqual(len(runner.calls), 1)

    def test_no_lifecycle_config_records_no_events(self):
        data = self.project()
        del data["lifecycle"]
        self.config_file().write_text(json.dumps(data))
        self._track(1, _OPEN_DRAFT)
        self._set_view(1, _MERGED)
        runner = FakeRunner([])
        self._sync(runner)
        self.assertEqual(runner.calls, [])
        self.assertEqual(self.ran_payloads(), [])

    def test_two_merges_in_one_sync_run_once(self):
        self._track(1, _OPEN_DRAFT)
        self._track(2, _OPEN_DRAFT)
        self._set_view(1, _MERGED)
        self._set_view(2, _MERGED)
        runner = FakeRunner([ok_result()])
        self._sync(runner)
        self.assertEqual(len(runner.calls), 1)
        self.assertEqual(self.ran_payloads()[0]["triggers"], ["acme/app#1", "acme/app#2"])

    def test_runs_after_merge_notice_and_fast_forward(self):
        self.run_cli(["raid", "join", "release", "--ttl", "1h"], "sess-1", self.repo_dir)
        self._track(1, _OPEN_DRAFT)
        self._set_view(1, _MERGED)
        order = []
        original = sync_commands._fast_forward_merged_bases_mutating_git

        def recording_fast_forward(ctx, projects, merged_repos):
            order.append("fast-forward")
            return original(ctx, projects, merged_repos)

        def runner(argv, cwd, timeout_seconds):
            notices = self.run_cli(["notices"], None, None)[1]
            order.append("run:merged-notice" if "acme/app#1 merged in main" in notices else "run:no-notice")
            return ok_result()

        with mock.patch.object(sync_commands, "_fast_forward_merged_bases_mutating_git", recording_fast_forward):
            self._sync(runner)
        self.assertEqual(order, ["fast-forward", "run:merged-notice"])

    def test_failing_command_does_not_fail_sync(self):
        self._track(1, _OPEN_DRAFT)
        self._set_view(1, _MERGED)
        code, out, err = self._sync(FakeRunner([failed_result()]))
        self.assertEqual(code, 0, err)
        self.assertNotIn("sync failed", err)
        self.assertEqual(len(self.notice_texts()), 1)
