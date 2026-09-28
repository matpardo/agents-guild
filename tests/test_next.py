import json
import sqlite3
from datetime import timedelta
from unittest import mock

from guild import timeutil
from tests.testutil import GuildTestCase


class NextTestCase(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha"], "sess-1", self.repo_dir)

    def _set_next_config(self, stale_hours):
        config_file = self.config_home / "guild" / "projects" / "acme.json"
        data = json.loads(config_file.read_text())
        data["next"] = {"stale_hours": stale_hours}
        config_file.write_text(json.dumps(data))

    def _pr_row(self, number=1):
        conn = sqlite3.connect(str(self.data_home / "guild" / "guild.db"))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM prs WHERE repo = 'acme/app' AND number = ?", (number,)).fetchone()
        conn.close()
        return row


class Tier1Tests(NextTestCase):
    def setUp(self):
        super().setUp()
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", self.repo_dir)
        self.run_cli(["task", "add", "demo/T01", "--title", "First"], "sess-1", self.repo_dir)
        self.write_gh_fixture(
            "view_acme-app_1",
            {"state": "OPEN", "isDraft": True, "headRefName": "feature/x", "title": "t"},
        )
        self.run_cli(
            ["pr", "track", "acme/app#1", "--task", "demo/T01", "--what", "x", "--waits", "y"],
            "sess-1", self.repo_dir,
        )

    def test_failing_checks_reported(self):
        self.write_gh_fixture(
            "view_acme-app_1",
            {
                "state": "OPEN", "isDraft": True, "headRefName": "feature/x", "title": "t",
                "statusCheckRollup": [{"conclusion": "FAILURE"}],
            },
        )
        self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["next"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0)
        self.assertIn("PR acme/app#1: failing checks (1 failing)", out)

    def test_merge_conflict_reported(self):
        self.write_gh_fixture(
            "view_acme-app_1",
            {
                "state": "OPEN", "isDraft": True, "headRefName": "feature/x", "title": "t",
                "mergeable": "CONFLICTING",
            },
        )
        self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["next"], "sess-1", self.repo_dir)
        self.assertIn("PR acme/app#1: merge conflict", out)

    def test_new_review_comments_acknowledged_on_single_next(self):
        self.write_gh_fixture(
            "view_acme-app_1",
            {
                "state": "OPEN", "isDraft": True, "headRefName": "feature/x", "title": "t",
                "comments": [{"id": 1}, {"id": 2}],
            },
        )
        self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["next"], "sess-1", self.repo_dir)
        self.assertIn("new review comments (2 unseen)", out)
        row = self._pr_row()
        self.assertEqual(row["last_notified_comment_count"], 2)

    def test_next_all_is_read_only(self):
        self.write_gh_fixture(
            "view_acme-app_1",
            {
                "state": "OPEN", "isDraft": True, "headRefName": "feature/x", "title": "t",
                "comments": [{"id": 1}],
            },
        )
        self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)
        self.run_cli(["next", "--all"], "sess-1", self.repo_dir)
        row = self._pr_row()
        self.assertEqual(row["last_notified_comment_count"], 0)


class Tier2Tests(NextTestCase):
    def setUp(self):
        super().setUp()
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", self.repo_dir)
        self.run_cli(["task", "add", "demo/T01", "--title", "First"], "sess-1", self.repo_dir)
        self.write_gh_fixture(
            "view_acme-app_1",
            {"state": "OPEN", "isDraft": True, "headRefName": "feature/x", "title": "t"},
        )
        self.run_cli(
            ["pr", "track", "acme/app#1", "--task", "demo/T01", "--what", "x", "--waits", "y"],
            "sess-1", self.repo_dir,
        )
        self.run_cli(["pr", "set", "acme/app#1", "--lifecycle", "needs-human"], "sess-1", self.repo_dir)

    def test_answered_ask_after_pr_set_is_reported(self):
        self.run_cli(
            ["ask", "one more round?", "--context", "ctx", "--ref", "pr:acme/app#1"], "sess-1", self.repo_dir
        )
        code, out, err = self.run_cli(["answer", "1", "ship it"], None, None)
        self.assertEqual(code, 0)
        code, out, err = self.run_cli(["next"], "sess-1", self.repo_dir)
        self.assertIn("PR acme/app#1: ask #1 answered: ship it", out)

    def test_answer_before_pr_set_is_not_reported(self):
        self.run_cli(
            ["ask", "one more round?", "--context", "ctx", "--ref", "pr:acme/app#1"], "sess-1", self.repo_dir
        )
        self.run_cli(["answer", "1", "ship it"], None, None)
        self.run_cli(["pr", "set", "acme/app#1", "--waits", "z"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["next"], "sess-1", self.repo_dir)
        self.assertNotIn("ask #1 answered", out)


class Tier3Tests(NextTestCase):
    def setUp(self):
        super().setUp()
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", self.repo_dir)
        self.run_cli(["task", "add", "demo/T01", "--title", "First"], "sess-1", self.repo_dir)
        self.write_gh_fixture(
            "view_acme-app_1",
            {"state": "OPEN", "isDraft": True, "headRefName": "feature/x", "title": "t"},
        )
        self.run_cli(
            ["pr", "track", "acme/app#1", "--task", "demo/T01", "--what", "x", "--waits", "y"],
            "sess-1", self.repo_dir,
        )
        self.run_cli(["pr", "set", "acme/app#1", "--lifecycle", "converging"], "sess-1", self.repo_dir)

    def test_stale_pr_reported_when_configured(self):
        self._set_next_config(8)
        future = timeutil.utcnow() + timedelta(hours=9)
        with mock.patch("guild.timeutil.utcnow", return_value=future):
            code, out, err = self.run_cli(["next"], "sess-1", self.repo_dir)
        self.assertIn("converging with no activity for 9h (> 8h)", out)

    def test_stale_pr_skipped_without_config(self):
        future = timeutil.utcnow() + timedelta(hours=9)
        with mock.patch("guild.timeutil.utcnow", return_value=future):
            code, out, err = self.run_cli(["next"], "sess-1", self.repo_dir)
        self.assertNotIn("converging", out)

    def test_fresh_pr_not_reported_as_stale(self):
        self._set_next_config(8)
        code, out, err = self.run_cli(["next"], "sess-1", self.repo_dir)
        self.assertNotIn("converging with no activity", out)


class Tier4Tests(NextTestCase):
    def setUp(self):
        super().setUp()
        self.sync_sdd(
            self.repo_dir,
            "sess-1",
            "acme",
            "compliance",
            "## T01 — First task\n\n**Deps:** —\n\n**Status:** [x] done\n\n"
            "## T02 — Second task\n\n**Deps:** T01\n\n**Status:** [ ] pending\n\n"
            "## T03 — Third task\n\n**Deps:** T02\n\n**Status:** [ ] pending\n",
        )
        self.run_cli(
            [
                "quest", "add", "wave1", "--title", "Wave 1", "--epic", "compliance",
                "--tasks", "T02,T03",
            ],
            "sess-1", self.repo_dir,
        )

    def test_next_task_when_deps_done(self):
        code, out, err = self.run_cli(["next"], "sess-1", self.repo_dir)
        self.assertIn("task wave1/T02: Second task — ready", out)

    def test_next_task_blocked_by_pending_dep_reports_source(self):
        self.sync_sdd(
            self.repo_dir,
            "sess-1",
            "acme",
            "compliance",
            "## T01 — First task\n\n**Deps:** —\n\n**Status:** [ ] pending\n\n"
            "## T02 — Second task\n\n**Deps:** T01\n\n**Status:** [ ] pending\n\n"
            "## T03 — Third task\n\n**Deps:** T02\n\n**Status:** [ ] pending\n",
        )
        code, out, err = self.run_cli(["next"], "sess-1", self.repo_dir)
        self.assertIn("nothing actionable", out)
        self.assertIn("wave1/T02: waiting on T01 (per sdd)", out)
        self.assertIn("wave1/T03: waiting on T02 (per guild)", out)

    def test_open_ask_blocks_task(self):
        self.run_cli(["ask", "which way?", "--context", "c", "--ref", "task:wave1/T02"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["next"], "sess-1", self.repo_dir)
        self.assertIn("nothing actionable", out)
        self.assertIn("wave1/T02: open ask #1", out)

    def test_claim_by_other_party_blocks_task(self):
        self.run_cli(["party", "start", "beta"], "sess-2", self.repo_dir)
        self.run_cli(["claim", "task:compliance/T02", "--ttl", "8h"], "sess-2", self.repo_dir)
        code, out, err = self.run_cli(["next"], "sess-1", self.repo_dir)
        self.assertIn("nothing actionable", out)
        self.assertIn("wave1/T02: claimed by beta", out)

    def test_claim_by_self_does_not_block_task(self):
        self.run_cli(["claim", "task:compliance/T02", "--ttl", "8h"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["next"], "sess-1", self.repo_dir)
        self.assertIn("task wave1/T02: Second task — ready", out)

    def test_nothing_queued_reports_nothing_actionable(self):
        self.run_cli(["task", "done", "wave1/T02"], "sess-1", self.repo_dir)
        self.run_cli(["task", "done", "wave1/T03"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["next"], "sess-1", self.repo_dir)
        self.assertIn("nothing actionable", out)

    def test_disagreement_between_guild_and_sdd_is_surfaced(self):
        self.sync_sdd(
            self.repo_dir,
            "sess-1",
            "acme",
            "compliance",
            "## T01 — First task\n\n**Deps:** —\n\n**Status:** [ ] pending\n\n"
            "## T02 — Second task\n\n**Deps:** T01\n\n**Status:** [ ] pending\n\n"
            "## T03 — Third task\n\n**Deps:** T02\n\n**Status:** [ ] pending\n",
        )
        self.run_cli(
            ["quest", "add", "wave0", "--title", "Wave 0", "--epic", "compliance", "--tasks", "T01"],
            "sess-1", self.repo_dir,
        )
        self.run_cli(["task", "done", "wave0/T01"], "sess-1", self.repo_dir)
        self.sync_sdd(
            self.repo_dir,
            "sess-1",
            "acme",
            "compliance",
            "## T01 — First task\n\n**Deps:** —\n\n**Status:** [ ] pending\n\n"
            "## T02 — Second task\n\n**Deps:** T01\n\n**Status:** [ ] pending\n\n"
            "## T03 — Third task\n\n**Deps:** T02\n\n**Status:** [ ] pending\n",
        )
        code, out, err = self.run_cli(["next"], "sess-1", self.repo_dir)
        self.assertIn("disagreement: compliance/T01: guild=done, sdd=pending", out)


class NextAllTests(NextTestCase):
    def test_all_lists_full_queue(self):
        self.sync_sdd(
            self.repo_dir,
            "sess-1",
            "acme",
            "compliance",
            "## T01 — First task\n\n**Deps:** —\n\n**Status:** [ ] pending\n",
        )
        self.run_cli(
            ["quest", "add", "wave1", "--title", "Wave 1", "--epic", "compliance", "--tasks", "T01"],
            "sess-1", self.repo_dir,
        )
        self.write_gh_fixture(
            "view_acme-app_1",
            {
                "state": "OPEN", "isDraft": True, "headRefName": "feature/x", "title": "t",
                "statusCheckRollup": [{"conclusion": "FAILURE"}],
            },
        )
        self.run_cli(
            ["pr", "track", "acme/app#1", "--task", "wave1/T01", "--what", "x", "--waits", "y"],
            "sess-1", self.repo_dir,
        )
        self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["next", "--all"], "sess-1", self.repo_dir)
        self.assertIn("PR acme/app#1: failing checks (1 failing)", out)
        self.assertIn("task wave1/T01: First task — ready", out)


if __name__ == "__main__":
    import unittest

    unittest.main()
