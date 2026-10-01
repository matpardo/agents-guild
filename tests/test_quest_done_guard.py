import json

from guild import db, paths
from tests.testutil import GuildTestCase


class QuestDoneGuardTestCase(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha"], "sess-1", self.repo_dir)

    def _cli(self, argv):
        return self.run_cli(argv, "sess-1", self.repo_dir)

    def _add_quest(self, tasks):
        argv = ["quest", "add", "demo", "--title", "Demo", "--no-epic"]
        if tasks:
            argv += ["--tasks", tasks]
        code, out, err = self._cli(argv)
        self.assertEqual(code, 0, err)

    def _state(self):
        conn = db.connect(paths.db_path())
        return conn.execute("SELECT state FROM quests WHERE slug = 'demo'").fetchone()["state"]

    def _done_snapshot(self):
        conn = db.connect(paths.db_path())
        row = conn.execute("SELECT payload FROM events WHERE kind = 'quest.done'").fetchone()
        return json.loads(row["payload"])["achievement"]


class GuardTests(QuestDoneGuardTestCase):
    def test_refuses_with_queued_active_and_blocked_tasks_listed(self):
        self._add_quest("T01,T02,T03,T04")
        self._cli(["task", "done", "demo/T01", "--summary", "ok"])
        self._cli(["task", "start", "demo/T02", "--summary", "wip"])
        self._cli(["task", "block", "demo/T03", "--reason", "ci"])
        code, out, err = self._cli(["quest", "done", "demo"])
        self.assertEqual(code, 1)
        self.assertIn("T02", err)
        self.assertIn("T03", err)
        self.assertIn("T04", err)
        self.assertNotIn("T01", err)
        self.assertIn("--force", err)
        self.assertEqual(self._state(), "active")

    def test_allows_when_all_tasks_done(self):
        self._add_quest("T01")
        self._cli(["task", "done", "demo/T01", "--summary", "ok"])
        code, out, err = self._cli(["quest", "done", "demo"])
        self.assertEqual(code, 0, err)
        self.assertEqual(self._state(), "done")

    def test_allows_quest_without_tasks(self):
        self._add_quest("")
        code, out, err = self._cli(["quest", "done", "demo"])
        self.assertEqual(code, 0, err)

    def test_force_overrides_and_snapshot_counts_only_done_tasks(self):
        self._add_quest("T01,T02")
        self._cli(["task", "done", "demo/T01", "--summary", "ok"])
        code, out, err = self._cli(["quest", "done", "demo", "--force"])
        self.assertEqual(code, 0, err)
        self.assertEqual(self._state(), "done")
        snapshot = self._done_snapshot()
        self.assertEqual(snapshot["tasks_done"], 1)
        self.assertEqual(snapshot["sdd_tids"], ["T01"])
