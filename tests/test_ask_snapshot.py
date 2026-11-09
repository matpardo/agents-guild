import json

from guild import db, events, paths, timeutil
from tests.testutil import GuildTestCase

_EPIC_TASKS = (
    "## T01 — First (PROJ-12)\n\n**Deps:** —\n\n**Status:** [ ] pending\n\n"
    "## T02 — Second\n\n**Deps:** —\n\n**Status:** [ ] pending\n"
)


class AskSnapshotBase(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(
            ["party", "start", "alpha", "--reason", "test reason", "--goal", "test goal", "--done-when", "test done"],
            "sess-1",
            self.repo_dir,
        )
        self.write_session(111, "sess-1", "alpha-g1")
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", self.repo_dir)
        self.run_cli(
            ["task", "add", "demo/T01", "--title", "First", "--reason", "serves the goal"], "sess-1", self.repo_dir
        )
        self.run_cli(
            ["task", "add", "demo/T02", "--title", "Second", "--reason", "serves the goal"], "sess-1", self.repo_dir
        )

    def ask(self, *extra):
        return self.run_cli(["ask", "which?", "--context", "x", *extra], "sess-1", self.repo_dir)

    def row(self):
        conn = db.connect(paths.db_path())
        return conn.execute("SELECT * FROM asks WHERE id = 1").fetchone()


class AutoRefTests(AskSnapshotBase):
    def test_single_active_task_is_added_and_reported(self):
        self.run_cli(["task", "start", "demo/T01"], "sess-1", self.repo_dir)
        code, out, err = self.ask()
        self.assertEqual(code, 0, err)
        self.assertIn("auto-ref: task:demo/T01", out)
        self.assertEqual(json.loads(self.row()["refs"]), ["task:demo/T01"])

    def test_explicit_task_ref_prevents_auto_ref(self):
        self.run_cli(["task", "start", "demo/T01"], "sess-1", self.repo_dir)
        code, out, err = self.ask("--ref", "task:demo/T02")
        self.assertEqual(code, 0, err)
        self.assertNotIn("auto-ref", out)
        self.assertEqual(json.loads(self.row()["refs"]), ["task:demo/T02"])

    def test_pr_only_ref_gets_the_single_active_task_added(self):
        self.run_cli(["task", "start", "demo/T01"], "sess-1", self.repo_dir)
        self.write_gh_fixture(
            "view_acme-app_1",
            {"state": "OPEN", "isDraft": True, "headRefName": "feature/1", "title": "t"},
        )
        self.run_cli(
            ["pr", "track", "acme/app#1", "--task", "demo/T02", "--what", "x", "--waits", "y"],
            "sess-1",
            self.repo_dir,
        )
        code, out, err = self.ask("--ref", "pr:acme/app#1")
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(self.row()["refs"]), ["pr:acme/app#1", "task:demo/T01"])

    def test_two_active_tasks_with_only_pr_refs_keep_refs_as_given(self):
        self.run_cli(["task", "start", "demo/T01"], "sess-1", self.repo_dir)
        self.run_cli(["task", "start", "demo/T02"], "sess-1", self.repo_dir)
        self.write_gh_fixture(
            "view_acme-app_1",
            {"state": "OPEN", "isDraft": True, "headRefName": "feature/1", "title": "t"},
        )
        self.run_cli(
            ["pr", "track", "acme/app#1", "--task", "demo/T02", "--what", "x", "--waits", "y"],
            "sess-1",
            self.repo_dir,
        )
        code, out, err = self.ask("--ref", "pr:acme/app#1")
        self.assertEqual(code, 0, err)
        self.assertNotIn("auto-ref", out)
        self.assertEqual(json.loads(self.row()["refs"]), ["pr:acme/app#1"])

    def test_two_active_tasks_and_no_ref_is_an_error(self):
        self.run_cli(["task", "start", "demo/T01"], "sess-1", self.repo_dir)
        self.run_cli(["task", "start", "demo/T02"], "sess-1", self.repo_dir)
        code, out, err = self.ask()
        self.assertEqual(code, 1)
        self.assertIn(
            "ask needs at least one --ref (no single in-progress task to reference automatically)",
            err,
        )

    def test_no_active_task_and_no_ref_is_an_error(self):
        code, out, err = self.ask()
        self.assertEqual(code, 1)
        self.assertIn("ask needs at least one --ref", err)

    def test_no_auto_ref_line_without_auto_ref(self):
        code, out, err = self.ask("--ref", "task:demo/T01")
        self.assertNotIn("auto-ref", out)


class SnapshotContentTests(AskSnapshotBase):
    def test_snapshot_records_origin(self):
        self.run_cli(["task", "start", "demo/T01"], "sess-1", self.repo_dir)
        self.ask()
        snapshot = json.loads(self.row()["snapshot"])
        self.assertEqual(snapshot["session_id"], "sess-1")
        self.assertEqual(snapshot["session_name"], "alpha-g1")
        self.assertEqual(snapshot["in_progress"], [{"quest": "demo", "tid": "T01", "title": "First"}])
        self.assertEqual(snapshot["epics"], [])
        self.assertEqual(snapshot["cards"], [])
        self.assertIsNone(snapshot["handoff_path"])

    def test_snapshot_collects_epics_cards_and_handoff(self):
        self.sync_sdd(self.repo_dir, "sess-1", "acme", "widget", _EPIC_TASKS)
        self.run_cli(
            ["quest", "add", "wq", "--title", "W", "--epic", "widget", "--tasks", "T01"],
            "sess-1",
            self.repo_dir,
        )
        self.run_cli(["task", "start", "wq/T01"], "sess-1", self.repo_dir)
        self.write_gh_fixture(
            "view_acme-app_2",
            {"state": "OPEN", "isDraft": True, "headRefName": "feature/2", "title": "t"},
        )
        self.track_legacy_card_pr("alpha", "acme/app", 2, "PROJ-99", "x", "y", "feature/2")
        conn = db.connect(paths.db_path())
        with db.writing(conn):
            conn.execute("UPDATE leaders SET handoff_path = '/tmp/alpha-g1.md' WHERE party = 'alpha'")
        self.ask("--ref", "task:wq/T01")
        snapshot = json.loads(self.row()["snapshot"])
        self.assertEqual(snapshot["epics"], ["widget"])
        self.assertEqual(snapshot["cards"], ["PROJ-12", "PROJ-99"])
        self.assertEqual(snapshot["handoff_path"], "/tmp/alpha-g1.md")


class SnapshotReducerTests(AskSnapshotBase):
    def _created(self, ask_id, extra):
        conn = db.connect(paths.db_path())
        payload = {
            "id": ask_id,
            "party": "alpha",
            "question": "q",
            "context": "x",
            "refs": ["task:demo/T01"],
            "options": [],
        }
        payload.update(extra)
        with db.writing(conn):
            events.record(
                conn,
                timeutil.utcnow(),
                "test@host",
                "alpha",
                None,
                "acme",
                "ask.created",
                "local",
                payload,
            )
        return conn

    def test_snapshot_is_stored_as_json(self):
        conn = self._created(1, {"snapshot": {"session_id": "sess-1"}})
        row = conn.execute("SELECT snapshot FROM asks WHERE id = 1").fetchone()
        self.assertEqual(json.loads(row["snapshot"]), {"session_id": "sess-1"})

    def test_missing_snapshot_is_null(self):
        conn = self._created(1, {})
        row = conn.execute("SELECT snapshot FROM asks WHERE id = 1").fetchone()
        self.assertIsNone(row["snapshot"])

    def test_event_without_recommend_rebuilds_with_null(self):
        conn = self._created(1, {})
        row = conn.execute("SELECT recommend FROM asks WHERE id = 1").fetchone()
        self.assertIsNone(row["recommend"])

    def test_rebuild_replays_the_snapshot(self):
        self.run_cli(["task", "start", "demo/T01"], "sess-1", self.repo_dir)
        self.ask()
        before = self.row()["snapshot"]
        code, out, err = self.run_cli(["rebuild"], None, None)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.row()["snapshot"], before)
        self.assertIsNotNone(before)
