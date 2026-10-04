import json
import os

from guild import db, paths
from guild.cli import _build_context
from guild.commands import dispatch as dispatch_commands
from tests.fake_tmux import FakeTmux
from tests.testutil import GuildTestCase

_FAILING = [{"conclusion": "FAILURE"}]
_FAILING_AND_PENDING = [{"conclusion": "FAILURE"}, {"status": "IN_PROGRESS", "conclusion": ""}]
_PASSING = [{"conclusion": "SUCCESS"}]


class ChecksFailingBase(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.write_block({"checks_failing": "on"})
        self.run_cli(["party", "start", "alpha"], "sess-1", self.repo_dir)
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", self.repo_dir)
        self.run_cli(["task", "add", "demo/T01", "--title", "First"], "sess-1", self.repo_dir)
        self.write_gh_fixture(
            "view_acme-app_1", {"state": "OPEN", "isDraft": True, "headRefName": "feature/x", "title": "t"}
        )
        code, out, err = self.run_cli(
            ["pr", "track", "acme/app#1", "--task", "demo/T01", "--what", "x", "--waits", "y"],
            "sess-1", self.repo_dir,
        )
        self.assertEqual(code, 0, err)
        self.run_cli(["handoff", "--in-flight", "x", "--learned", "y"], "sess-1", self.repo_dir)
        self.tmux = FakeTmux(True, True, {}, 0)
        self.pushes = []
        self.run_pass()

    def write_block(self, rules):
        path = self.config_home / "guild" / "projects" / "acme.json"
        data = json.loads(path.read_text())
        data["dispatcher"] = {"permission_mode": "acceptEdits", "max_launches_per_hour": 5, "rules": rules}
        path.write_text(json.dumps(data))

    def set_repos(self, repos):
        path = self.config_home / "guild" / "projects" / "acme.json"
        data = json.loads(path.read_text())
        data["github"]["repos"] = repos
        path.write_text(json.dumps(data))

    def sync(self, rollup, head_sha, is_draft, state, merged_at):
        fixture = {
            "state": state, "isDraft": is_draft, "headRefName": "feature/x", "title": "t",
            "statusCheckRollup": rollup,
        }
        if head_sha is not None:
            fixture["headRefOid"] = head_sha
        if merged_at is not None:
            fixture["mergedAt"] = merged_at
        self.write_gh_fixture("view_acme-app_1", fixture)
        code, out, err = self.run_cli(["sync", "--source", "gh"], None, self.repo_dir)
        self.assertEqual(code, 0, err)

    def sync_open(self, rollup, head_sha):
        self.sync(rollup, head_sha, True, "OPEN", None)

    def sync_cross_repository(self, cross_repository):
        self.write_gh_fixture(
            "view_acme-app_1",
            {
                "state": "OPEN", "isDraft": True, "headRefName": "feature/x", "title": "t",
                "statusCheckRollup": _FAILING, "headRefOid": "abc123", "isCrossRepository": cross_repository,
            },
        )
        code, out, err = self.run_cli(["sync", "--source", "gh"], None, self.repo_dir)
        self.assertEqual(code, 0, err)

    def run_pass(self):
        ctx = _build_context(None, self.repo_dir)
        try:
            return dispatch_commands.run(ctx, False, self.tmux, self.pushes.append)
        finally:
            ctx.conn.close()

    def decision_keys(self):
        conn = db.connect(paths.db_path())
        try:
            rows = conn.execute("SELECT key FROM dispatch_decisions ORDER BY key").fetchall()
        finally:
            conn.close()
        return [row["key"] for row in rows]


class FailingChecksTests(ChecksFailingBase):
    def test_settled_failing_checks_launch_the_pr_owner(self):
        self.sync_open(_FAILING, "abc123")
        lines = self.run_pass()
        self.assertEqual(
            lines, ["acme: checks_failing acme/app#1 -> launched alpha g2 (window @10, mode acceptEdits)"]
        )
        self.assertEqual(self.decision_keys(), ["checks_failing:acme/app#1:abc123"])
        self.assertEqual(len(self.tmux.launch_calls()), 1)

    def test_prompt_names_only_the_pr_and_the_checks_command(self):
        self.sync_open(_FAILING, "abc123")
        self.run_pass()
        command = self.tmux.launch_calls()[0][-1]
        self.assertTrue(
            command.endswith(
                "'Continue the work described in the guild brief."
                " Dispatched: checks fail on acme/app#1; run gh pr checks 1 --repo acme/app.'"
            )
        )
        self.assertNotIn("abc123", command)

    def test_pending_checks_launch_nothing_until_they_settle(self):
        self.sync_open(_FAILING_AND_PENDING, "abc123")
        self.assertEqual(self.run_pass(), ["nothing to dispatch"])
        self.sync_open(_FAILING, "abc123")
        self.assertEqual(len(self.run_pass()), 1)
        self.assertEqual(len(self.tmux.launch_calls()), 1)

    def test_same_head_decides_once_across_passes(self):
        self.write_block({"checks_failing": "dry-run"})
        self.sync_open(_FAILING, "abc123")
        self.run_pass()
        self.sync_open(_FAILING, "abc123")
        self.assertEqual(self.run_pass(), ["nothing to dispatch"])
        self.assertEqual(self.decision_keys(), ["checks_failing:acme/app#1:abc123"])

    def test_new_failing_head_decides_again(self):
        self.write_block({"checks_failing": "dry-run"})
        self.sync_open(_FAILING, "abc123")
        self.run_pass()
        self.sync_open(_FAILING, "def456")
        lines = self.run_pass()
        self.assertEqual(len(lines), 1)
        self.assertEqual(
            self.decision_keys(), ["checks_failing:acme/app#1:abc123", "checks_failing:acme/app#1:def456"]
        )

    def test_passing_checks_launch_nothing(self):
        self.sync_open(_PASSING, "abc123")
        self.assertEqual(self.run_pass(), ["nothing to dispatch"])

    def test_ready_lifecycle_also_triggers(self):
        self.sync(_FAILING, "abc123", False, "OPEN", None)
        self.assertEqual(len(self.run_pass()), 1)

    def test_merged_pr_launches_nothing(self):
        self.sync(_FAILING, "abc123", False, "MERGED", "2026-10-04T00:00:00Z")
        self.assertEqual(self.run_pass(), ["nothing to dispatch"])

    def test_closed_pr_launches_nothing(self):
        self.sync(_FAILING, "abc123", True, "CLOSED", None)
        self.assertEqual(self.run_pass(), ["nothing to dispatch"])

    def test_seeded_pr_launches_nothing(self):
        conn = db.connect(paths.db_path())
        conn.execute("UPDATE prs SET seeded = 1")
        conn.close()
        self.sync_open(_FAILING, "abc123")
        self.assertEqual(self.run_pass(), ["nothing to dispatch"])

    def test_repo_outside_the_project_launches_nothing(self):
        self.set_repos(["acme/other"])
        self.sync_open(_FAILING, "abc123")
        self.assertEqual(self.run_pass(), ["nothing to dispatch"])

    def test_pr_from_a_fork_launches_nothing(self):
        self.sync_cross_repository(True)
        self.assertEqual(self.run_pass(), ["nothing to dispatch"])
        self.assertEqual(self.tmux.launch_calls(), [])

    def test_pr_from_the_base_repository_launches(self):
        self.sync_cross_repository(False)
        self.assertEqual(len(self.run_pass()), 1)

    def test_deferred_failing_checks_launch_once_the_session_ends(self):
        self.write_session(os.getpid(), "sess-1", "alpha")
        self.sync_open(_FAILING, "abc123")
        lines = self.run_pass()
        self.assertEqual(lines, ["acme: checks_failing acme/app#1 -> deferred alpha: live session"])
        (self.sessions_dir / "{}.json".format(os.getpid())).unlink()
        lines = self.run_pass()
        self.assertEqual(
            lines, ["acme: checks_failing acme/app#1 -> launched alpha g2 (window @10, mode acceptEdits)"]
        )
        self.assertEqual(self.run_pass(), ["nothing to dispatch"])

    def test_deferred_checks_that_turn_green_launch_nothing(self):
        self.write_session(os.getpid(), "sess-1", "alpha")
        self.sync_open(_FAILING, "abc123")
        self.run_pass()
        self.sync_open(_PASSING, "abc123")
        (self.sessions_dir / "{}.json".format(os.getpid())).unlink()
        self.assertEqual(self.run_pass(), ["nothing to dispatch"])
        self.assertEqual(self.tmux.launch_calls(), [])

    def test_missing_head_commit_launches_nothing(self):
        self.sync_open(_FAILING, None)
        self.assertEqual(self.run_pass(), ["nothing to dispatch"])

    def test_rule_absent_from_config_launches_nothing(self):
        self.write_block({"ask_answered": "on"})
        self.sync_open(_FAILING, "abc123")
        self.assertEqual(self.run_pass(), ["nothing to dispatch"])
