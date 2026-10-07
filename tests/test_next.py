import json
import sqlite3
from datetime import timedelta
from unittest import mock

from guild import timeutil
from guild.cli import _build_context
from guild.commands import next as next_commands
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

    def test_legacy_pr_without_notified_count_does_not_crash(self):
        self.write_gh_fixture(
            "view_acme-app_1",
            {
                "state": "OPEN", "isDraft": True, "headRefName": "feature/x", "title": "t",
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
        self.run_cli(["pr", "set", "acme/app#1", "--needs-ask-answer"], "sess-1", self.repo_dir)

    def test_answered_ask_after_pr_set_is_reported(self):
        self.run_cli(
            ["ask", "one more round?", "--context", "ctx", "--ref", "pr:acme/app#1"], "sess-1", self.repo_dir
        )
        code, out, err = self.run_cli(["answer", "1", "ship it"], None, None)
        self.assertEqual(code, 0)
        code, out, err = self.run_cli(["next"], "sess-1", self.repo_dir)
        self.assertIn("PR acme/app#1: ask #1 answered: ship it", out)

    def test_answered_ask_is_not_reported_when_the_flag_is_off(self):
        self.run_cli(["pr", "set", "acme/app#1", "--no-needs-ask-answer"], "sess-1", self.repo_dir)
        self.run_cli(
            ["ask", "one more round?", "--context", "ctx", "--ref", "pr:acme/app#1"], "sess-1", self.repo_dir
        )
        self.run_cli(["answer", "1", "ship it"], None, None)
        code, out, err = self.run_cli(["next"], "sess-1", self.repo_dir)
        self.assertNotIn("ask #1 answered", out)

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
        self.assertIn('task wave1/T02: "Second task" — ready', out)

    def test_task_added_to_an_epic_quest_is_queued(self):
        self.run_cli(["task", "start", "wave1/T02"], "sess-1", self.repo_dir)
        self.run_cli(["task", "done", "wave1/T02"], "sess-1", self.repo_dir)
        self.run_cli(["task", "start", "wave1/T03"], "sess-1", self.repo_dir)
        self.run_cli(["task", "done", "wave1/T03"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(
            ["task", "add", "wave1/T09", "--title", "Extra"], "sess-1", self.repo_dir
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
        self.run_cli(["party", "start", "beta"], "sess-2", self.repo_dir)
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
        self.assertIn('task wave1/T01: "First task" — ready', out)


class LeadRaidWorkTests(NextTestCase):
    def setUp(self):
        super().setUp()
        self.run_cli(["raid", "join", "ci", "--until-leave", "--lead"], "sess-1", self.repo_dir)
        self.run_cli(["party", "start", "beta"], "sess-2", self.repo_dir)
        self.run_cli(["raid", "join", "ci", "--until-leave"], "sess-2", self.repo_dir)
        self.run_cli(["quest", "add", "bq", "--title", "B", "--no-epic"], "sess-2", self.repo_dir)
        self.run_cli(["task", "add", "bq/T01", "--title", "First"], "sess-2", self.repo_dir)

    def _beta_asks(self):
        self.run_cli(["ask", "ready?", "--context", "x", "--ref", "task:bq/T01"], "sess-2", self.repo_dir)

    def _view(self, conclusion):
        return {
            "state": "OPEN", "isDraft": False, "headRefName": "feature/y", "title": "t",
            "statusCheckRollup": [{"conclusion": conclusion}], "mergeable": "MERGEABLE",
        }

    def _beta_tracks_pr(self):
        self.write_gh_fixture("view_acme-app_7", self._view("SUCCESS"))
        self.write_gh_fixture(
            "view_files_acme-app_7",
            {"files": [{"path": "a.py"}], "additions": 1, "deletions": 1, "createdAt": "2026-09-03T10:00:00Z"},
        )
        self.run_cli(
            ["pr", "track", "acme/app#7", "--task", "bq/T01", "--what", "x", "--waits", "y"],
            "sess-2", self.repo_dir,
        )
        self.run_cli(["pr", "set", "acme/app#7", "--lifecycle", "ready"], "sess-2", self.repo_dir)
        self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)

    def _event_count(self):
        conn = sqlite3.connect(str(self.data_home / "guild" / "guild.db"))
        count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        conn.close()
        return count

    def test_open_member_ask_listed_instead_of_nothing_actionable(self):
        self._beta_asks()
        code, out, err = self.run_cli(["next"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        self.assertIn('raid ci: ask #1 from beta: "ready?"', out)
        self.assertNotIn("nothing actionable", out)

    def test_answered_member_ask_not_listed(self):
        self._beta_asks()
        self.run_cli(["answer", "1", "go"], None, None)
        code, out, err = self.run_cli(["next"], "sess-1", self.repo_dir)
        self.assertIn("nothing actionable", out)

    def test_own_ask_not_listed(self):
        self.run_cli(["ask", "mine?", "--context", "x", "--ref", "task:bq/T01"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["next"], "sess-1", self.repo_dir)
        self.assertNotIn("raid ci: ask", out)

    def test_non_lead_member_sees_nothing_of_it(self):
        self._beta_asks()
        code, out, err = self.run_cli(["next"], "sess-2", self.repo_dir)
        self.assertNotIn("raid ci", out)

    def test_merge_queue_entry_listed_with_reason(self):
        self._beta_tracks_pr()
        code, out, err = self.run_cli(["next"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        self.assertIn("raid ci: merge queue 1. acme/app#7 beta", out)
        self.assertNotIn("nothing actionable", out)

    def test_blocked_merge_queue_entry_listed_with_its_fix_action(self):
        self._beta_tracks_pr()
        self.write_gh_fixture("view_acme-app_7", self._view("FAILURE"))
        self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["next"], "sess-1", self.repo_dir)
        self.assertIn("raid ci: merge queue 1. acme/app#7 beta \u2014 fix: checks failing (1) \u2192 beta", out)

    def test_red_main_listed_before_the_queue(self):
        self._beta_tracks_pr()
        self.run_cli(["main", "red", "acme/app", "--reason", "ci down"], None, self.repo_dir)
        code, out, err = self.run_cli(["next"], "sess-1", self.repo_dir)
        self.assertIn("raid ci: MAIN RED acme/app \u2014 ci down (manual) \u2192 fix before anything", out)

    def test_all_lists_asks_and_queue_entries(self):
        self._beta_asks()
        self._beta_tracks_pr()
        code, out, err = self.run_cli(["next", "--all"], "sess-1", self.repo_dir)
        self.assertIn('raid ci: ask #1 from beta: "ready?"', out)
        self.assertIn("raid ci: merge queue 1. acme/app#7 beta", out)

    def test_ask_listed_before_merge_queue_in_single_mode(self):
        self._beta_asks()
        self._beta_tracks_pr()
        code, out, err = self.run_cli(["next"], "sess-1", self.repo_dir)
        self.assertIn("raid ci: ask #1", out)
        self.assertNotIn("merge queue", out)

    def test_next_never_changes_state(self):
        self._beta_asks()
        self._beta_tracks_pr()
        before = self._event_count()
        self.run_cli(["next"], "sess-1", self.repo_dir)
        self.run_cli(["next", "--all"], "sess-1", self.repo_dir)
        self.assertEqual(self._event_count(), before)

    def test_own_task_ranks_before_raid_work(self):
        self._beta_asks()
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", self.repo_dir)
        self.run_cli(["task", "add", "demo/T01", "--title", "First"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["next"], "sess-1", self.repo_dir)
        self.assertIn("task demo/T01", out)
        self.assertNotIn("raid ci", out)


class HasWorkTests(NextTestCase):
    def _has_work(self):
        ctx = _build_context("sess-1", self.repo_dir)
        binding = {"party": "alpha", "project": "acme", "generation": 1}
        return next_commands.has_work(ctx, binding)

    def _event_count(self):
        conn = sqlite3.connect(str(self.data_home / "guild" / "guild.db"))
        count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        conn.close()
        return count

    def _track_pr_with_comments(self):
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", self.repo_dir)
        self.run_cli(["task", "add", "demo/T01", "--title", "First"], "sess-1", self.repo_dir)
        self.run_cli(["task", "start", "demo/T01"], "sess-1", self.repo_dir)
        self.write_gh_fixture(
            "view_acme-app_1",
            {
                "state": "OPEN", "isDraft": True, "headRefName": "feature/x", "title": "t",
                "comments": [{"id": 1}, {"id": 2}],
            },
        )
        self.run_cli(
            ["pr", "track", "acme/app#1", "--task", "demo/T01", "--what", "x", "--waits", "y"],
            "sess-1", self.repo_dir,
        )
        self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)

    def test_false_when_nothing_to_do(self):
        self.assertFalse(self._has_work())

    def test_true_with_queued_task(self):
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", self.repo_dir)
        self.run_cli(["task", "add", "demo/T01", "--title", "First"], "sess-1", self.repo_dir)
        self.assertTrue(self._has_work())

    def test_true_with_unseen_comments_without_acknowledging_or_writing(self):
        self._track_pr_with_comments()
        before = self._event_count()
        self.assertTrue(self._has_work())
        self.assertEqual(self._event_count(), before)
        self.assertEqual(self._pr_row()["last_notified_comment_count"], 0)

    def test_false_when_raid_paused(self):
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", self.repo_dir)
        self.run_cli(["task", "add", "demo/T01", "--title", "First"], "sess-1", self.repo_dir)
        self.run_cli(["raid", "join", "ci", "--until-leave", "--lead"], "sess-1", self.repo_dir)
        self.run_cli(["raid", "pause", "ci"], "sess-1", self.repo_dir)
        self.assertFalse(self._has_work())


class NextTaskItemTests(NextTestCase):
    def _item(self, project="acme"):
        ctx = _build_context("sess-1", self.repo_dir)
        item = next_commands.next_task_item(ctx, {"party": "alpha", "project": project})
        ctx.conn.close()
        return item

    def _add_task(self):
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", self.repo_dir)
        self.run_cli(["task", "add", "demo/T01", "--title", "First"], "sess-1", self.repo_dir)

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
        self.run_cli(["raid", "join", "ci", "--until-leave", "--lead"], "sess-1", self.repo_dir)
        self.run_cli(["raid", "pause", "ci"], "sess-1", self.repo_dir)
        self.assertIsNone(self._item())


class Tier0Tests(NextTestCase):
    def setUp(self):
        super().setUp()
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", self.repo_dir)
        self.run_cli(["task", "add", "demo/T01", "--title", "First"], "sess-1", self.repo_dir)

    def _track(self, number, extra):
        self.write_gh_fixture(
            "view_acme-app_{}".format(number),
            {"state": "OPEN", "isDraft": True, "headRefName": "fix/x", "title": "t"},
        )
        code, out, err = self.run_cli(
            [
                "pr", "track", "acme/app#{}".format(number), "--task", "demo/T01",
                "--what", "x", "--waits", "y",
            ] + extra,
            "sess-1", self.repo_dir,
        )
        self.assertEqual(code, 0, err)

    def _fail_checks(self, number):
        self.write_gh_fixture(
            "view_acme-app_{}".format(number),
            {
                "state": "OPEN", "isDraft": True, "headRefName": "fix/x", "title": "t",
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
