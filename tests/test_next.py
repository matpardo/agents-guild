import json
import sqlite3
from datetime import timedelta
from unittest import mock

from guild import party_status, pr_records, timeutil, work_queue
from guild.cli import _build_context
from tests.testutil import GuildTestCase


class NextTestCase(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(
            ["party", "start", "alpha", "--reason", "test reason", "--goal", "test goal", "--done-when", "test done"],
            "sess-1",
            self.repo_dir,
        )

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
        self.run_cli(
            ["task", "add", "demo/T01", "--title", "First", "--reason", "serves the goal"], "sess-1", self.repo_dir
        )
        self.write_gh_fixture(
            "view_acme-app_1",
            {"state": "OPEN", "isDraft": True, "headRefName": "feature/x", "title": "t"},
        )
        self.run_cli(
            ["pr", "track", "acme/app#1", "--task", "demo/T01", "--what", "x", "--waits", "y"],
            "sess-1",
            self.repo_dir,
        )

    def test_failing_checks_reported(self):
        self.write_gh_fixture(
            "view_acme-app_1",
            {
                "state": "OPEN",
                "isDraft": True,
                "headRefName": "feature/x",
                "title": "t",
                "statusCheckRollup": [{"conclusion": "FAILURE"}],
            },
        )
        self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["next"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0)
        self.assertIn("PR acme/app#1: failing checks (1 failing)", out)

    def test_billing_failing_checks_not_reported(self):
        self.write_gh_fixture(
            "view_acme-app_1",
            {
                "state": "OPEN",
                "isDraft": True,
                "headRefName": "feature/x",
                "title": "t",
                "statusCheckRollup": [{"conclusion": "FAILURE"}],
            },
        )
        self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)
        conn = sqlite3.connect(str(self.data_home / "guild" / "guild.db"))
        conn.execute("UPDATE prs SET checks_billing = 1 WHERE number = 1")
        conn.commit()
        conn.close()
        code, out, err = self.run_cli(["next"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0)
        self.assertNotIn("failing checks", out)

    def test_real_failing_checks_classification_reported(self):
        self.write_gh_fixture(
            "view_acme-app_1",
            {
                "state": "OPEN",
                "isDraft": True,
                "headRefName": "feature/x",
                "title": "t",
                "statusCheckRollup": [{"conclusion": "FAILURE"}],
            },
        )
        self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)
        conn = sqlite3.connect(str(self.data_home / "guild" / "guild.db"))
        conn.execute("UPDATE prs SET checks_billing = 0 WHERE number = 1")
        conn.commit()
        conn.close()
        code, out, err = self.run_cli(["next"], "sess-1", self.repo_dir)
        self.assertIn("PR acme/app#1: failing checks (1 failing)", out)

    def test_merge_conflict_reported(self):
        self.write_gh_fixture(
            "view_acme-app_1",
            {
                "state": "OPEN",
                "isDraft": True,
                "headRefName": "feature/x",
                "title": "t",
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
                "state": "OPEN",
                "isDraft": True,
                "headRefName": "feature/x",
                "title": "t",
                "comments": [{"id": 1}, {"id": 2}],
            },
        )
        self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["next"], "sess-1", self.repo_dir)
        self.assertIn("new review comments (2 unseen)", out)
        row = self._pr_row()
        self.assertEqual(row["last_notified_comment_count"], 2)

    def test_legacy_pr_without_notified_count_does_not_crash(self):
        self.write_gh_fixture(
            "view_acme-app_1",
            {
                "state": "OPEN",
                "isDraft": True,
                "headRefName": "feature/x",
                "title": "t",
                "comments": [{"id": 1}, {"id": 2}],
            },
        )
        self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)
        conn = sqlite3.connect(str(self.data_home / "guild" / "guild.db"))
        conn.execute("UPDATE prs SET last_notified_comment_count = NULL")
        conn.commit()
        conn.close()
        code, out, err = self.run_cli(["next"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        self.assertIn("new review comments (2 unseen)", out)
        code, out, err = self.run_cli(["next", "--all"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)

    def test_next_all_is_read_only(self):
        self.write_gh_fixture(
            "view_acme-app_1",
            {
                "state": "OPEN",
                "isDraft": True,
                "headRefName": "feature/x",
                "title": "t",
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
        self.run_cli(
            ["task", "add", "demo/T01", "--title", "First", "--reason", "serves the goal"], "sess-1", self.repo_dir
        )
        self.write_gh_fixture(
            "view_acme-app_1",
            {"state": "OPEN", "isDraft": True, "headRefName": "feature/x", "title": "t"},
        )
        self.run_cli(
            ["pr", "track", "acme/app#1", "--task", "demo/T01", "--what", "x", "--waits", "y"],
            "sess-1",
            self.repo_dir,
        )
        self.run_cli(["pr", "set", "acme/app#1", "--needs-ask-answer"], "sess-1", self.repo_dir)

    def test_answered_ask_after_pr_set_is_reported(self):
        self.run_cli(["ask", "one more round?", "--context", "ctx", "--ref", "pr:acme/app#1"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["answer", "1", "ship it"], None, None)
        self.assertEqual(code, 0)
        code, out, err = self.run_cli(["next"], "sess-1", self.repo_dir)
        self.assertIn("PR acme/app#1: ask #1 answered: ship it", out)

    def test_answered_ask_is_not_reported_when_the_flag_is_off(self):
        self.run_cli(["pr", "set", "acme/app#1", "--no-needs-ask-answer"], "sess-1", self.repo_dir)
        self.run_cli(["ask", "one more round?", "--context", "ctx", "--ref", "pr:acme/app#1"], "sess-1", self.repo_dir)
        self.run_cli(["answer", "1", "ship it"], None, None)
        code, out, err = self.run_cli(["next"], "sess-1", self.repo_dir)
        self.assertNotIn("ask #1 answered", out)

    def test_answer_before_pr_set_is_not_reported(self):
        self.run_cli(["ask", "one more round?", "--context", "ctx", "--ref", "pr:acme/app#1"], "sess-1", self.repo_dir)
        self.run_cli(["answer", "1", "ship it"], None, None)
        self.run_cli(["pr", "set", "acme/app#1", "--waits", "z"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["next"], "sess-1", self.repo_dir)
        self.assertNotIn("ask #1 answered", out)


class Tier3Tests(NextTestCase):
    def setUp(self):
        super().setUp()
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", self.repo_dir)
        self.run_cli(
            ["task", "add", "demo/T01", "--title", "First", "--reason", "serves the goal"], "sess-1", self.repo_dir
        )
        self.write_gh_fixture(
            "view_acme-app_1",
            {"state": "OPEN", "isDraft": True, "headRefName": "feature/x", "title": "t"},
        )
        self.run_cli(
            ["pr", "track", "acme/app#1", "--task", "demo/T01", "--what", "x", "--waits", "y"],
            "sess-1",
            self.repo_dir,
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
                "quest",
                "add",
                "wave1",
                "--title",
                "Wave 1",
                "--epic",
                "compliance",
                "--tasks",
                "T02,T03",
            ],
            "sess-1",
            self.repo_dir,
        )

    def _sync_all_done(self):
        self.sync_sdd(
            self.repo_dir,
            "sess-1",
            "acme",
            "compliance",
            "## T01 — First task\n\n**Deps:** —\n\n**Status:** [x] done\n\n"
            "## T02 — Second task\n\n**Deps:** T01\n\n**Status:** [x] done\n\n"
            "## T03 — Third task\n\n**Deps:** T02\n\n**Status:** [x] done\n",
        )

    def test_next_task_when_deps_done(self):
        code, out, err = self.run_cli(["next"], "sess-1", self.repo_dir)
        self.assertIn('task wave1/T02: "Second task" — ready', out)

    def test_task_added_to_an_epic_quest_is_queued(self):
        self.run_cli(["task", "start", "wave1/T02"], "sess-1", self.repo_dir)
        self.run_cli(["task", "done", "wave1/T02"], "sess-1", self.repo_dir)
        self.run_cli(["task", "start", "wave1/T03"], "sess-1", self.repo_dir)
        self.run_cli(["task", "done", "wave1/T03"], "sess-1", self.repo_dir)
        self._sync_all_done()
        code, out, err = self.run_cli(
            ["task", "add", "wave1/T09", "--title", "Extra", "--reason", "serves the goal"], "sess-1", self.repo_dir
        )
        self.assertEqual(code, 0, err)
        code, out, err = self.run_cli(["next"], "sess-1", self.repo_dir)
        self.assertIn('task wave1/T09: "Extra" — ready', out)

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
        self.run_cli(
            ["party", "start", "beta", "--reason", "test reason", "--goal", "test goal", "--done-when", "test done"],
            "sess-2",
            self.repo_dir,
        )
        self.run_cli(["claim", "task:compliance/T02", "--ttl", "8h"], "sess-2", self.repo_dir)
        code, out, err = self.run_cli(["next"], "sess-1", self.repo_dir)
        self.assertIn("nothing actionable", out)
        self.assertIn("wave1/T02: claimed by beta", out)

    def test_claim_by_self_does_not_block_task(self):
        self.run_cli(["claim", "task:compliance/T02", "--ttl", "8h"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["next"], "sess-1", self.repo_dir)
        self.assertIn('task wave1/T02: "Second task" — ready', out)

    def test_nothing_queued_reports_nothing_actionable(self):
        self.run_cli(["task", "done", "wave1/T02"], "sess-1", self.repo_dir)
        self.run_cli(["task", "done", "wave1/T03"], "sess-1", self.repo_dir)
        self._sync_all_done()
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
            "sess-1",
            self.repo_dir,
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
            "sess-1",
            self.repo_dir,
        )
        self.write_gh_fixture(
            "view_acme-app_1",
            {
                "state": "OPEN",
                "isDraft": True,
                "headRefName": "feature/x",
                "title": "t",
                "statusCheckRollup": [{"conclusion": "FAILURE"}],
            },
        )
        self.run_cli(
            ["pr", "track", "acme/app#1", "--task", "wave1/T01", "--what", "x", "--waits", "y"],
            "sess-1",
            self.repo_dir,
        )
        self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["next", "--all"], "sess-1", self.repo_dir)
        self.assertIn("PR acme/app#1: failing checks (1 failing)", out)
        self.assertIn('task wave1/T01: "First task" — ready', out)


class RaidMemberWorkTests(NextTestCase):
    def setUp(self):
        super().setUp()
        self.run_cli(["raid", "join", "ci", "--until-leave"], "sess-1", self.repo_dir)
        self.run_cli(
            ["party", "start", "beta", "--reason", "test reason", "--goal", "test goal", "--done-when", "test done"],
            "sess-2",
            self.repo_dir,
        )
        self.run_cli(["raid", "join", "ci", "--until-leave"], "sess-2", self.repo_dir)
        self.run_cli(["quest", "add", "bq", "--title", "B", "--no-epic"], "sess-2", self.repo_dir)
        self.run_cli(
            ["task", "add", "bq/T01", "--title", "First", "--reason", "serves the goal"], "sess-2", self.repo_dir
        )

    def _beta_asks(self):
        self.run_cli(["ask", "ready?", "--context", "x", "--ref", "task:bq/T01"], "sess-2", self.repo_dir)

    def _view(self, conclusion):
        return {
            "state": "OPEN",
            "isDraft": False,
            "headRefName": "feature/y",
            "title": "t",
            "statusCheckRollup": [{"conclusion": conclusion}],
            "mergeable": "MERGEABLE",
        }

    def _beta_tracks_pr(self):
        self.write_gh_fixture("view_acme-app_7", self._view("SUCCESS"))
        self.write_gh_fixture(
            "view_files_acme-app_7",
            {"files": [{"path": "a.py"}], "additions": 1, "deletions": 1, "createdAt": "2026-09-03T10:00:00Z"},
        )
        self.run_cli(
            ["pr", "track", "acme/app#7", "--task", "bq/T01", "--what", "x", "--waits", "y"],
            "sess-2",
            self.repo_dir,
        )
        self.run_cli(["pr", "set", "acme/app#7", "--lifecycle", "ready"], "sess-2", self.repo_dir)
        self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)

    def test_member_ask_is_not_listed_for_other_members(self):
        self._beta_asks()
        code, out, err = self.run_cli(["next"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        self.assertEqual(out, "nothing actionable\n")

    def test_raid_merge_queue_is_not_listed_for_members(self):
        self._beta_tracks_pr()
        code, out, err = self.run_cli(["next", "--all"], "sess-1", self.repo_dir)
        self.assertNotIn("raid ci", out)
        self.assertNotIn("merge queue", out)


class HasWorkTests(NextTestCase):
    def _has_work(self):
        ctx = _build_context("sess-1", self.repo_dir)
        binding = {"party": "alpha", "project": "acme", "generation": 1}
        return work_queue.has_work(ctx, binding)

    def _event_count(self):
        conn = sqlite3.connect(str(self.data_home / "guild" / "guild.db"))
        count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        conn.close()
        return count

    def _track_pr_with_comments(self):
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", self.repo_dir)
        self.run_cli(
            ["task", "add", "demo/T01", "--title", "First", "--reason", "serves the goal"], "sess-1", self.repo_dir
        )
        self.run_cli(["task", "start", "demo/T01"], "sess-1", self.repo_dir)
        self.write_gh_fixture(
            "view_acme-app_1",
            {
                "state": "OPEN",
                "isDraft": True,
                "headRefName": "feature/x",
                "title": "t",
                "comments": [{"id": 1}, {"id": 2}],
            },
        )
        self.run_cli(
            ["pr", "track", "acme/app#1", "--task", "demo/T01", "--what", "x", "--waits", "y"],
            "sess-1",
            self.repo_dir,
        )
        self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)

    def test_false_when_nothing_to_do(self):
        self.assertFalse(self._has_work())

    def test_true_with_queued_task(self):
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", self.repo_dir)
        self.run_cli(
            ["task", "add", "demo/T01", "--title", "First", "--reason", "serves the goal"], "sess-1", self.repo_dir
        )
        self.assertTrue(self._has_work())

    def test_true_with_unseen_comments_without_acknowledging_or_writing(self):
        self._track_pr_with_comments()
        before = self._event_count()
        self.assertTrue(self._has_work())
        self.assertEqual(self._event_count(), before)
        self.assertEqual(self._pr_row()["last_notified_comment_count"], 0)

    def test_false_when_raid_paused(self):
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", self.repo_dir)
        self.run_cli(
            ["task", "add", "demo/T01", "--title", "First", "--reason", "serves the goal"], "sess-1", self.repo_dir
        )
        self.run_cli(["raid", "join", "ci", "--until-leave"], "sess-1", self.repo_dir)
        self.run_cli(["raid", "pause", "ci"], "sess-1", self.repo_dir)
        self.assertFalse(self._has_work())


class NextTaskItemTests(NextTestCase):
    def _item(self, project="acme"):
        ctx = _build_context("sess-1", self.repo_dir)
        item = work_queue.next_task_item(ctx, {"party": "alpha", "project": project})
        ctx.conn.close()
        return item

    def _add_task(self):
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", self.repo_dir)
        self.run_cli(
            ["task", "add", "demo/T01", "--title", "First", "--reason", "serves the goal"], "sess-1", self.repo_dir
        )

    def test_returns_queued_task(self):
        self._add_task()
        item = self._item()
        self.assertEqual((item["quest"], item["tid"], item["title"]), ("demo", "T01", "First"))

    def test_none_without_tasks(self):
        self.assertIsNone(self._item())

    def test_none_without_project(self):
        self._add_task()
        self.assertIsNone(self._item(None))

    def test_none_when_raid_paused(self):
        self._add_task()
        self.run_cli(["raid", "join", "ci", "--until-leave"], "sess-1", self.repo_dir)
        self.run_cli(["raid", "pause", "ci"], "sess-1", self.repo_dir)
        self.assertIsNone(self._item())


class Tier0Tests(NextTestCase):
    def setUp(self):
        super().setUp()
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", self.repo_dir)
        self.run_cli(
            ["task", "add", "demo/T01", "--title", "First", "--reason", "serves the goal"], "sess-1", self.repo_dir
        )

    def _track(self, number, extra):
        self.write_gh_fixture(
            "view_acme-app_{}".format(number),
            {"state": "OPEN", "isDraft": True, "headRefName": "fix/x", "title": "t"},
        )
        code, out, err = self.run_cli(
            [
                "pr",
                "track",
                "acme/app#{}".format(number),
                "--task",
                "demo/T01",
                "--what",
                "x",
                "--waits",
                "y",
            ]
            + extra,
            "sess-1",
            self.repo_dir,
        )
        self.assertEqual(code, 0, err)

    def _fail_checks(self, number):
        self.write_gh_fixture(
            "view_acme-app_{}".format(number),
            {
                "state": "OPEN",
                "isDraft": True,
                "headRefName": "fix/x",
                "title": "t",
                "statusCheckRollup": [{"conclusion": "FAILURE"}],
            },
        )
        self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)

    def test_a_healthy_main_fix_is_the_next_item(self):
        self._track(1, ["--fixes-main"])
        code, out, err = self.run_cli(["next"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        self.assertIn("PR acme/app#1: fixes a broken main — land it first", out)

    def test_a_healthy_flaky_fix_is_the_next_item(self):
        self._track(1, ["--fixes-flaky"])
        code, out, err = self.run_cli(["next"], "sess-1", self.repo_dir)
        self.assertIn("PR acme/app#1: fixes flaky tests — land it first", out)

    def test_both_marks_are_named_in_one_reason(self):
        self._track(1, ["--fixes-main", "--fixes-flaky"])
        code, out, err = self.run_cli(["next"], "sess-1", self.repo_dir)
        self.assertIn("fixes a broken main and flaky tests — land it first", out)

    def test_a_marked_pr_comes_before_a_pr_with_failing_checks(self):
        self._track(1, [])
        self._track(2, ["--fixes-main"])
        self._fail_checks(1)
        code, out, err = self.run_cli(["next"], "sess-1", self.repo_dir)
        self.assertIn("PR acme/app#2: fixes a broken main — land it first", out)
        self.assertNotIn("acme/app#1", out)

    def test_a_marked_pr_with_failing_checks_is_listed_once(self):
        self._track(1, ["--fixes-main"])
        self._fail_checks(1)
        code, out, err = self.run_cli(["next", "--all"], "sess-1", self.repo_dir)
        self.assertEqual(out.count("PR acme/app#1"), 1)
        self.assertIn("fixes a broken main — land it first", out)

    def test_an_unmarked_pr_still_leads_when_nothing_is_marked(self):
        self._track(1, [])
        self._fail_checks(1)
        code, out, err = self.run_cli(["next"], "sess-1", self.repo_dir)
        self.assertIn("PR acme/app#1: failing checks (1 failing)", out)


if __name__ == "__main__":
    import unittest

    unittest.main()


class MaxOpenPrsTests(NextTestCase):
    def setUp(self):
        super().setUp()
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", self.repo_dir)
        for tid in ("T01", "T02", "T03"):
            self.run_cli(
                ["task", "add", "demo/{}".format(tid), "--title", tid, "--reason", "serves the goal"],
                "sess-1",
                self.repo_dir,
            )
        self._track(1, "T01")
        self._track(2, "T02")
        self.run_cli(["task", "start", "demo/T01"], "sess-1", self.repo_dir)
        self.run_cli(["task", "start", "demo/T02"], "sess-1", self.repo_dir)

    def _track(self, number, tid):
        self.write_gh_fixture(
            "view_acme-app_{}".format(number),
            {"state": "OPEN", "isDraft": True, "headRefName": "feature/{}".format(number), "title": "t"},
        )
        self.run_cli(
            [
                "pr",
                "track",
                "acme/app#{}".format(number),
                "--task",
                "demo/{}".format(tid),
                "--what",
                "x",
                "--waits",
                "y",
            ],
            "sess-1",
            self.repo_dir,
        )

    def _set_cap(self, cap, key="max_open_prs_per_party"):
        config_file = self.config_home / "guild" / "projects" / "acme.json"
        data = json.loads(config_file.read_text())
        data[key] = cap
        config_file.write_text(json.dumps(data))

    def _hand_prs_to_other_party(self):
        conn = sqlite3.connect(str(self.data_home / "guild" / "guild.db"))
        conn.execute("INSERT INTO parties (name, project, generation, state) VALUES ('beta', 'acme', 1, 'active')")
        conn.execute("UPDATE prs SET party = 'beta'")
        conn.commit()
        conn.close()

    def test_project_cap_reached_by_other_parties_blocks_caller(self):
        self._hand_prs_to_other_party()
        self._set_cap(2, "max_open_prs")
        self._set_cap(3)
        code, out, err = self.run_cli(["next"], "sess-1", self.repo_dir)
        self.assertEqual(out.strip(), "wait: 2 open PRs in project, merge acme/app#1 first")

    def test_project_cap_not_reached_offers_task(self):
        self._hand_prs_to_other_party()
        self._set_cap(3, "max_open_prs")
        code, out, err = self.run_cli(["next"], "sess-1", self.repo_dir)
        self.assertIn("task demo/T03", out)

    def test_party_message_wins_when_both_caps_reached(self):
        self._set_cap(2, "max_open_prs")
        self._set_cap(2)
        code, out, err = self.run_cli(["next"], "sess-1", self.repo_dir)
        self.assertEqual(out.strip(), "wait: 2 open PRs, merge acme/app#1 first")

    def test_absent_cap_offers_task(self):
        code, out, err = self.run_cli(["next"], "sess-1", self.repo_dir)
        self.assertIn("task demo/T03", out)

    def test_below_cap_offers_task(self):
        self._set_cap(3)
        code, out, err = self.run_cli(["next"], "sess-1", self.repo_dir)
        self.assertIn("task demo/T03", out)

    def test_cap_reached_waits_on_first_queue_pr(self):
        self._set_cap(2)
        code, out, err = self.run_cli(["next"], "sess-1", self.repo_dir)
        self.assertEqual(out.strip(), "wait: 2 open PRs, merge acme/app#1 first")

    def test_all_shows_wait_line_without_task(self):
        self._set_cap(2)
        code, out, err = self.run_cli(["next", "--all"], "sess-1", self.repo_dir)
        self.assertIn("wait: 2 open PRs, merge acme/app#1 first", out)
        self.assertNotIn("task demo/T03", out)

    def test_merged_and_closed_prs_are_not_counted(self):
        self._set_cap(2)
        self.write_gh_fixture(
            "view_acme-app_1",
            {
                "state": "MERGED",
                "isDraft": False,
                "headRefName": "feature/1",
                "title": "t",
                "mergedAt": "2026-01-01T00:00:00Z",
            },
        )
        self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["next"], "sess-1", self.repo_dir)
        self.assertIn("task demo/T03", out)


class WipOneTests(NextTestCase):
    def setUp(self):
        super().setUp()
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", self.repo_dir)
        for tid in ("T01", "T02"):
            self.run_cli(
                ["task", "add", "demo/{}".format(tid), "--title", tid, "--reason", "serves the goal"],
                "sess-1",
                self.repo_dir,
            )
        self.run_cli(["task", "start", "demo/T01"], "sess-1", self.repo_dir)

    def _track(self, lifecycle, extra_args):
        self.write_gh_fixture(
            "view_acme-app_1",
            {"state": "OPEN", "isDraft": lifecycle != "ready", "headRefName": "feature/1", "title": "t"},
        )
        code, out, err = self.run_cli(
            ["pr", "track", "acme/app#1", "--what", "x", "--waits", "y"] + extra_args, "sess-1", self.repo_dir
        )
        self.assertEqual(code, 0, err)
        self.run_cli(["pr", "set", "acme/app#1", "--lifecycle", lifecycle], "sess-1", self.repo_dir)

    def _update_pr(self, assignments):
        conn = sqlite3.connect(str(self.data_home / "guild" / "guild.db"))
        conn.execute("UPDATE prs SET {} WHERE number = 1".format(assignments))
        conn.commit()
        conn.close()

    def _next(self, args):
        code, out, err = self.run_cli(args, "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        return out

    def test_ready_pr_with_comment_after_head_holds_new_task(self):
        self._track("ready", ["--task", "demo/T01"])
        self._update_pr("comments_after_head = 1, ci_label = 1, checks_passing = 1")
        self.assertEqual(
            self._next(["next"]).strip(),
            "wait: acme/app#1 is not human-ready (1 comment after head), resolve it first",
        )

    def test_ready_pr_with_label_and_no_checks_holds_new_task(self):
        self._track("ready", ["--task", "demo/T01"])
        self._update_pr("comments_after_head = 0, ci_label = 1")
        self.assertEqual(
            self._next(["next"]).strip(),
            "wait: acme/app#1 is not human-ready (no checks on head), resolve it first",
        )

    def test_null_ci_label_and_no_checks_does_not_hold(self):
        self._track("ready", ["--task", "demo/T01"])
        self._update_pr("comments_after_head = 0, ci_label = NULL")
        self.assertIn("task demo/T02", self._next(["next"]))

    def test_null_ci_label_no_checks_and_comment_after_head_holds(self):
        self._track("ready", ["--task", "demo/T01"])
        self._update_pr("comments_after_head = 1, ci_label = NULL")
        self.assertEqual(
            self._next(["next"]).strip(),
            "wait: acme/app#1 is not human-ready (1 comment after head; no checks on head), resolve it first",
        )

    def test_open_ask_hold_names_the_ask_reason(self):
        self._track("ready", ["--task", "demo/T01"])
        self._update_pr("ci_label = 1, checks_passing = 1")
        self.run_cli(["ask", "ship it?", "--context", "c", "--ref", "pr:acme/app#1"], "sess-1", self.repo_dir)
        out = self._next(["next"]).strip()
        self.assertTrue(out.startswith("wait: acme/app#1 is not human-ready ("), out)
        self.assertIn("ask", out)
        self.assertTrue(out.endswith("resolve it first"), out)

    def test_manually_blocked_pr_does_not_hold(self):
        self._track("ready", ["--task", "demo/T01"])
        self._update_pr("comments_after_head = 1, ci_label = 1, checks_passing = 1")
        self.run_cli(["pr", "set", "acme/app#1", "--blocked-external", "waiting on vendor"], "sess-1", self.repo_dir)
        self.assertIn("task demo/T02", self._next(["next"]))

    def test_pr_behind_a_predecessor_names_the_wait(self):
        self._track("ready", ["--task", "demo/T01"])
        self.write_gh_fixture(
            "view_acme-app_2",
            {"state": "OPEN", "isDraft": True, "headRefName": "feature/2", "title": "t"},
        )
        self.track_legacy_card_pr("alpha", "acme/app", 2, "ACME-2", "x", "y", "feature/2")
        self._update_pr("ci_label = 1, checks_passing = 1")
        self.run_cli(["merge-queue", "pin", "acme/app#2", "--before", "acme/app#1"], "sess-1", self.repo_dir)
        self.assertEqual(
            self._next(["next"]).strip(),
            "wait: acme/app#1 is not human-ready (waits on acme/app#2), resolve it first",
        )

    def test_cap_line_wins_over_wip_hold(self):
        self._track("ready", ["--task", "demo/T01"])
        self._update_pr("comments_after_head = 1, ci_label = 1, checks_passing = 1")
        config_file = self.config_home / "guild" / "projects" / "acme.json"
        data = json.loads(config_file.read_text())
        data["max_open_prs_per_party"] = 1
        config_file.write_text(json.dumps(data))
        self.assertEqual(self._next(["next"]).strip(), "wait: 1 open PRs, merge acme/app#1 first")

    def test_party_with_held_pr_and_queued_task_reads_as_having_work(self):
        self._track("ready", ["--task", "demo/T01"])
        self._update_pr("comments_after_head = 1, ci_label = 1, checks_passing = 1")
        ctx = _build_context("sess-1", self.repo_dir)
        binding = {"party": "alpha", "project": "acme"}
        self.assertTrue(work_queue.has_work(ctx, binding))
        party_row = ctx.conn.execute("SELECT * FROM parties WHERE name = 'alpha'").fetchone()
        self.assertEqual(party_status.derive(ctx, party_row)["status"], "queued")

    def test_wip_queue_not_loaded_without_ready_own_pr(self):
        self._track("draft", ["--task", "demo/T01"])
        with mock.patch.object(pr_records, "load_scoped_queue") as loader:
            self._next(["next"])
        loader.assert_not_called()

    def test_ready_pr_waiting_only_for_ci_label_does_not_hold(self):
        self._track("ready", ["--task", "demo/T01"])
        self._update_pr("comments_after_head = 0, ci_label = 0")
        self.assertIn("task demo/T02", self._next(["next"]))

    def test_draft_pr_does_not_hold(self):
        self._track("draft", ["--task", "demo/T01"])
        self._update_pr("comments_after_head = 1, ci_label = 1")
        self.assertIn("task demo/T02", self._next(["next"]))

    def test_converging_pr_does_not_hold(self):
        self._track("converging", ["--task", "demo/T01"])
        self._update_pr("comments_after_head = 1, ci_label = 1")
        self.assertIn("task demo/T02", self._next(["next"]))

    def test_human_ready_pr_does_not_hold(self):
        self._track("ready", ["--task", "demo/T01"])
        self._update_pr("comments_after_head = 0, ci_label = 1, checks_passing = 1")
        self.assertIn("task demo/T02", self._next(["next"]))

    def test_other_party_pr_does_not_hold(self):
        self._track("ready", ["--task", "demo/T01"])
        self._update_pr("comments_after_head = 1, ci_label = 1, checks_passing = 1")
        conn = sqlite3.connect(str(self.data_home / "guild" / "guild.db"))
        conn.execute("INSERT INTO parties (name, project, generation, state) VALUES ('beta', 'acme', 1, 'active')")
        conn.execute("UPDATE prs SET party = 'beta'")
        conn.commit()
        conn.close()
        self.assertIn("task demo/T02", self._next(["next"]))

    def test_failing_checks_tier_keeps_priority(self):
        self._track("ready", ["--task", "demo/T01"])
        self._update_pr("comments_after_head = 1, ci_label = 1, checks_failing = 1")
        self.assertIn("PR acme/app#1: failing checks (1 failing)", self._next(["next"]))

    def test_all_lists_the_hold_without_task(self):
        self._track("ready", ["--task", "demo/T01"])
        self._update_pr("comments_after_head = 1, ci_label = 1, checks_passing = 1")
        out = self._next(["next", "--all"])
        self.assertIn("wait: acme/app#1 is not human-ready (1 comment after head), resolve it first", out)
        self.assertNotIn("task demo/T02", out)

    def test_loose_card_pr_holds_new_task(self):
        self.write_gh_fixture(
            "view_acme-app_1",
            {"state": "OPEN", "isDraft": False, "headRefName": "feature/1", "title": "t"},
        )
        self.track_legacy_card_pr("alpha", "acme/app", 1, "ACME-1", "x", "y", "feature/1")
        self.run_cli(["pr", "set", "acme/app#1", "--lifecycle", "ready"], "sess-1", self.repo_dir)
        self._update_pr("comments_after_head = 1, ci_label = 1, checks_passing = 1")
        self.assertIn("is not human-ready", self._next(["next"]))
