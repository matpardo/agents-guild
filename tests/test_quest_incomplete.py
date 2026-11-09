import json

from guild import db, paths
from tests.testutil import GuildTestCase


class QuestIncompleteTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self._cli(
            ["party", "start", "alpha", "--reason", "test reason", "--goal", "test goal", "--done-when", "test done"],
            "sess-1",
        )
        self._cli(["quest", "add", "demo", "--title", "Demo", "--no-epic", "--tasks", "T01,T02"], "sess-1")

    def _cli(self, argv, session):
        return self.run_cli(argv, session, self.repo_dir)

    def _finish(self):
        code, out, err = self._cli(["quest", "done", "demo", "--force"], "sess-1")
        self.assertEqual(code, 0, err)

    def _events(self):
        conn = db.connect(paths.db_path())
        return conn.execute("SELECT visibility, payload FROM events WHERE kind = 'quest.marked_incomplete'").fetchall()

    def test_marks_done_quest_incomplete_and_records_event(self):
        self._finish()
        code, out, err = self._cli(["quest", "incomplete", "demo", "--reason", "abandoned"], "sess-1")
        self.assertEqual(code, 0, err)
        self.assertIn("quest 'demo' marked incomplete", out)
        rows = self._events()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["visibility"], "local")
        self.assertEqual(json.loads(rows[0]["payload"]), {"slug": "demo", "reason": "abandoned"})

    def test_requires_reason(self):
        self._finish()
        code, out, err = self._cli(["quest", "incomplete", "demo"], "sess-1")
        self.assertEqual(code, 2)

    def test_rejects_blank_reason(self):
        self._finish()
        code, out, err = self._cli(["quest", "incomplete", "demo", "--reason", "  "], "sess-1")
        self.assertEqual(code, 1)
        self.assertIn("reason", err)
        self.assertEqual(self._events(), [])

    def test_refuses_active_quest(self):
        code, out, err = self._cli(["quest", "incomplete", "demo", "--reason", "x"], "sess-1")
        self.assertEqual(code, 1)
        self.assertIn("quest 'demo' is not done", err)
        self.assertEqual(self._events(), [])

    def test_refuses_unknown_quest(self):
        code, out, err = self._cli(["quest", "incomplete", "ghost", "--reason", "x"], "sess-1")
        self.assertEqual(code, 1)
        self.assertIn("unknown quest 'ghost'", err)

    def test_refuses_other_party(self):
        self._finish()
        self._cli(
            ["party", "start", "beta", "--reason", "test reason", "--goal", "test goal", "--done-when", "test done"],
            "sess-2",
        )
        code, out, err = self._cli(["quest", "incomplete", "demo", "--reason", "x"], "sess-2")
        self.assertEqual(code, 1)
        self.assertIn("not owned by party 'beta'", err)

    def test_refuses_second_marking(self):
        self._finish()
        self._cli(["quest", "incomplete", "demo", "--reason", "x"], "sess-1")
        code, out, err = self._cli(["quest", "incomplete", "demo", "--reason", "y"], "sess-1")
        self.assertEqual(code, 1)
        self.assertIn("already marked incomplete", err)
        self.assertEqual(len(self._events()), 1)

    def test_export_treats_event_as_local(self):
        self._finish()
        self._cli(["quest", "incomplete", "demo", "--reason", "x"], "sess-1")
        code, out, err = self.run_cli(["export", "--visibility", "guild"], None, None)
        self.assertEqual(code, 0, err)
        self.assertNotIn("quest.marked_incomplete", out)

    def test_rebuild_accepts_event(self):
        self._finish()
        self._cli(["quest", "incomplete", "demo", "--reason", "x"], "sess-1")
        code, out, err = self.run_cli(["rebuild"], None, None)
        self.assertEqual(code, 0, err)
        conn = db.connect(paths.db_path())
        self.assertEqual(conn.execute("SELECT state FROM quests").fetchone()["state"], "done")
