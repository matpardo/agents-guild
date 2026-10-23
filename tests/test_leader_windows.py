import json

from guild import db, events, paths, timeutil
from guild.cli import _build_context
from guild.commands import revive
from tests.test_revive import FakeTmux
from tests.testutil import GuildTestCase


class LeaderWindowsBase(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha"], "sess-1", self.repo_dir)
        self.conn = db.connect(paths.db_path())

    def tearDown(self):
        self.conn.close()
        super().tearDown()

    def _launched(self, generation, window_id):
        with db.writing(self.conn):
            events.record(
                self.conn, timeutil.utcnow(), "tester@host", "alpha", None, "acme", "leader.window_launched", "local",
                {"party": "alpha", "generation": generation, "window_id": window_id},
            )

    def _windows(self):
        rows = self.conn.execute(
            "SELECT generation, window_id FROM leader_windows WHERE party = 'alpha' ORDER BY generation"
        ).fetchall()
        return [(row["generation"], row["window_id"]) for row in rows]


class LeaderWindowsProjectionTests(LeaderWindowsBase):
    def test_launch_event_records_window_per_generation(self):
        self._launched(1, "@1")
        self._launched(2, "@2")
        self.assertEqual(self._windows(), [(1, "@1"), (2, "@2")])

    def test_relaunching_same_generation_replaces_window(self):
        self._launched(1, "@1")
        self._launched(1, "@9")
        self.assertEqual(self._windows(), [(1, "@9")])

    def test_resume_removes_records_of_older_generations(self):
        self._launched(1, "@1")
        self._launched(2, "@2")
        self.run_cli(["handoff", "--in-flight", "x", "--learned", "y"], "sess-1", self.repo_dir)
        self.run_cli(["party", "resume", "alpha"], "sess-2", self.repo_dir)
        self.assertEqual(self._windows(), [(2, "@2")])

    def test_close_removes_all_records(self):
        self._launched(1, "@1")
        self.run_cli(["party", "close", "alpha", "--pending", "none"], None, None)
        self.assertEqual(self._windows(), [])

    def test_rebuild_reproduces_records(self):
        self._launched(1, "@1")
        self._launched(2, "@2")
        self.run_cli(["rebuild"], None, None)
        self.assertEqual(self._windows(), [(1, "@1"), (2, "@2")])


class ReviveRecordsWindowsTests(LeaderWindowsBase):
    def setUp(self):
        super().setUp()
        self.work = self.repo_dir.parent / "work"
        self.work.mkdir()
        self.run_cli(["party", "start", "beta"], "sess-b", self.work)

    def _transcript(self, session_id):
        directory = self.claude_projects_dir / "-w"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "{}.jsonl".format(session_id)).write_text(json.dumps({"cwd": str(self.work)}) + "\n")

    def _revive(self, party):
        ctx = _build_context(None, self.root)
        return revive.run(ctx, [party], False, False, self.claude_projects_dir, FakeTmux(True, (), ()), None)

    def _windows_of(self, party):
        rows = self.conn.execute(
            "SELECT generation, window_id FROM leader_windows WHERE party = ?", (party,)
        ).fetchall()
        return [(row["generation"], row["window_id"]) for row in rows]

    def test_resume_launch_records_current_generation(self):
        self._transcript("sess-b")
        self._revive("beta")
        self.assertEqual(self._windows_of("beta"), [(1, "@1")])

    def test_fresh_launch_records_next_generation(self):
        self._revive("beta")
        self.assertEqual(self._windows_of("beta"), [(2, "@1")])

    def test_skipped_party_records_nothing(self):
        with db.writing(self.conn):
            self.conn.execute("UPDATE leaders SET cwd = ? WHERE party = 'beta'", (str(self.root / "gone"),))
        out = self._revive("beta")
        self.assertIn("skipped beta", out)
        self.assertEqual(self._windows_of("beta"), [])
