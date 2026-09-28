from guild import db, paths, resolve
from tests.testutil import GuildTestCase


class ResolveTaskDoneTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha"], "sess-1", self.repo_dir)
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
            "sess-1", self.repo_dir,
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


if __name__ == "__main__":
    import unittest

    unittest.main()
