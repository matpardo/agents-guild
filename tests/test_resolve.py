from guild import db, events, paths, resolve, timeutil
from tests.testutil import GuildTestCase


class ResolveTaskDoneTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha", "--reason", "test reason"], "sess-1", self.repo_dir)
        self.sync_sdd(
            self.repo_dir,
            "sess-1",
            "acme",
            "compliance",
            "## T01 — First\n\n**Deps:** —\n\n**Status:** [x] done\n\n"
            "## T02 — Second\n\n**Deps:** T01\n\n**Status:** [ ] pending\n",
        )
        self.run_cli(
            ["quest", "add", "wave1", "--title", "Wave 1", "--epic", "compliance", "--tasks", "T01,T02"],
            "sess-1",
            self.repo_dir,
        )
        self.conn = db.connect(paths.db_path())

    def test_no_opinion_anywhere_is_not_done(self):
        is_done, source, disagreements = resolve.resolve_task_done(self.conn, "acme", "unknown-epic", "T01")
        self.assertFalse(is_done)
        self.assertIsNone(source)
        self.assertEqual(disagreements, [])

    def test_guild_queued_overrides_sdd_done_and_flags_disagreement(self):
        is_done, source, disagreements = resolve.resolve_task_done(self.conn, "acme", "compliance", "T01")
        self.assertFalse(is_done)
        self.assertEqual(source, "guild")
        self.assertEqual(disagreements, [("guild", False), ("sdd", True)])

    def test_sdd_only_opinion_is_used_when_no_quest_took_the_task(self):
        self.sync_sdd(
            self.repo_dir,
            "sess-1",
            "acme",
            "standalone",
            "## T01 — Solo task\n\n**Deps:** —\n\n**Status:** [x] done\n",
        )
        is_done, source, disagreements = resolve.resolve_task_done(self.conn, "acme", "standalone", "T01")
        self.assertTrue(is_done)
        self.assertEqual(source, "sdd")
        self.assertEqual(disagreements, [])

    def test_guild_opinion_scoped_to_project(self):
        is_done, source, disagreements = resolve.resolve_task_done(self.conn, "other", "compliance", "T01")
        self.assertIsNone(source)
        self.assertEqual(disagreements, [])

    def test_guild_done_overrides_sdd_pending(self):
        self.run_cli(["task", "done", "wave1/T02"], "sess-1", self.repo_dir)
        is_done, source, disagreements = resolve.resolve_task_done(self.conn, "acme", "compliance", "T02")
        self.assertTrue(is_done)
        self.assertEqual(source, "guild")
        self.assertEqual(disagreements, [("guild", True), ("sdd", False)])

    def test_guild_and_sdd_agree_no_disagreement(self):
        self.run_cli(["task", "start", "wave1/T02"], "sess-1", self.repo_dir)
        is_done, source, disagreements = resolve.resolve_task_done(self.conn, "acme", "compliance", "T02")
        self.assertFalse(is_done)
        self.assertEqual(source, "guild")
        self.assertEqual(disagreements, [])


class TrackerOpinionTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha", "--reason", "test reason"], "sess-1", self.repo_dir)
        self.sync_sdd(
            self.repo_dir,
            "sess-1",
            "acme",
            "tracked",
            "## T01 → DEMO-1 — First\n\n**Deps:** —\n\n**Status:** [ ] pending\n\n"
            "## T02 → DEMO-2 — Second\n\n**Deps:** —\n\n**Status:** [x] done\n\n"
            "## T03 — Unkeyed\n\n**Deps:** —\n\n**Status:** [ ] pending\n",
        )
        self.conn = db.connect(paths.db_path())
        self._record_cards(
            [
                {
                    "key": "DEMO-1",
                    "status": "Done",
                    "status_category": "done",
                    "issue_type": "Task",
                    "parent_key": None,
                },
                {
                    "key": "DEMO-2",
                    "status": "In Progress",
                    "status_category": "indeterminate",
                    "issue_type": "Task",
                    "parent_key": None,
                },
            ]
        )

    def _record_cards(self, cards):
        with db.writing(self.conn):
            events.record(
                self.conn,
                timeutil.utcnow(),
                "test@host",
                None,
                None,
                "acme",
                "tracker.synced",
                "local",
                {"project": "acme", "cards": cards},
            )

    def test_tracker_done_overrides_sdd_pending(self):
        is_done, source, disagreements = resolve.resolve_task_done(self.conn, "acme", "tracked", "T01")
        self.assertTrue(is_done)
        self.assertEqual(source, "tracker")
        self.assertEqual(disagreements, [("tracker", True), ("sdd", False)])

    def test_tracker_in_progress_overrides_sdd_done(self):
        is_done, source, disagreements = resolve.resolve_task_done(self.conn, "acme", "tracked", "T02")
        self.assertFalse(is_done)
        self.assertEqual(source, "tracker")
        self.assertEqual(disagreements, [("tracker", False), ("sdd", True)])

    def test_task_without_key_falls_back_to_sdd(self):
        is_done, source, disagreements = resolve.resolve_task_done(self.conn, "acme", "tracked", "T03")
        self.assertEqual(source, "sdd")

    def test_key_without_synced_card_falls_back_to_sdd(self):
        self._record_cards([])
        is_done, source, disagreements = resolve.resolve_task_done(self.conn, "acme", "tracked", "T01")
        self.assertFalse(is_done)
        self.assertEqual(source, "sdd")

    def test_guild_overrides_tracker(self):
        self.run_cli(
            ["quest", "add", "wave1", "--title", "Wave 1", "--epic", "tracked", "--tasks", "T01"],
            "sess-1",
            self.repo_dir,
        )
        is_done, source, disagreements = resolve.resolve_task_done(self.conn, "acme", "tracked", "T01")
        self.assertFalse(is_done)
        self.assertEqual(source, "guild")
        self.assertEqual(disagreements, [("guild", False), ("tracker", True), ("sdd", False)])


if __name__ == "__main__":
    import unittest

    unittest.main()
