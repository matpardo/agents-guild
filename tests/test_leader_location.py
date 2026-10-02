import os
from unittest import mock

from guild import db, paths
from tests.test_migration import _make_old_schema_db
from tests.testutil import GuildTestCase


def _located_events(conn):
    return conn.execute("SELECT * FROM events WHERE kind = 'leader.located' ORDER BY seq").fetchall()


def _leader(conn, party, generation):
    return conn.execute(
        "SELECT * FROM leaders WHERE party = ? AND generation = ?", (party, generation)
    ).fetchone()


class LeaderLocationHookTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha"], "sess-1", self.repo_dir)
        self.other_dir = self.root / "elsewhere"
        self.other_dir.mkdir()

    def _conn(self):
        return db.connect(paths.db_path())

    def _start(self, cwd, permission_mode):
        payload = {"session_id": "sess-1", "cwd": str(cwd)}
        if permission_mode is not None:
            payload["permission_mode"] = permission_mode
        return self.run_hook("session-start", payload)

    def test_party_start_locates_with_process_cwd(self):
        leader = _leader(self._conn(), "alpha", 1)
        self.assertEqual(leader["cwd"], str(self.repo_dir.resolve()))
        self.assertIsNone(leader["permission_mode"])
        self.assertEqual(len(_located_events(self._conn())), 1)

    def test_hook_records_cwd_and_permission_mode(self):
        self._start(self.other_dir, "acceptEdits")
        conn = self._conn()
        leader = _leader(conn, "alpha", 1)
        self.assertEqual(leader["cwd"], str(self.other_dir))
        self.assertEqual(leader["permission_mode"], "acceptEdits")
        event = _located_events(conn)[-1]
        self.assertEqual(event["visibility"], "local")
        self.assertEqual(event["session_id"], "sess-1")
        self.assertIn('"generation": 1', event["payload"])
        self.assertIn('"party": "alpha"', event["payload"])

    def test_same_values_again_emit_no_event(self):
        self._start(self.other_dir, "acceptEdits")
        count = len(_located_events(self._conn()))
        self._start(self.other_dir, "acceptEdits")
        self.assertEqual(len(_located_events(self._conn())), count)

    def test_changed_cwd_emits_new_event(self):
        self._start(self.other_dir, "acceptEdits")
        count = len(_located_events(self._conn()))
        self._start(self.repo_dir, "acceptEdits")
        conn = self._conn()
        self.assertEqual(len(_located_events(conn)), count + 1)
        self.assertEqual(_leader(conn, "alpha", 1)["cwd"], str(self.repo_dir))

    def test_changed_permission_mode_emits_new_event(self):
        self._start(self.other_dir, "acceptEdits")
        count = len(_located_events(self._conn()))
        self._start(self.other_dir, "plan")
        conn = self._conn()
        self.assertEqual(len(_located_events(conn)), count + 1)
        self.assertEqual(_leader(conn, "alpha", 1)["permission_mode"], "plan")

    def test_missing_permission_mode_keeps_known_one(self):
        self._start(self.other_dir, "plan")
        count = len(_located_events(self._conn()))
        self._start(self.other_dir, None)
        conn = self._conn()
        self.assertEqual(len(_located_events(conn)), count)
        self.assertEqual(_leader(conn, "alpha", 1)["permission_mode"], "plan")

    def test_unbound_session_emits_nothing(self):
        code, out, err = self.run_hook(
            "session-start",
            {"session_id": "sess-9", "cwd": str(self.other_dir), "permission_mode": "plan"},
        )
        self.assertEqual(code, 0)
        self.assertEqual(len(_located_events(self._conn())), 1)

    def test_resume_locates_new_generation(self):
        self.run_cli(["handoff", "--in-flight", "x", "--learned", "y"], "sess-1", self.repo_dir)
        self.run_cli(["party", "resume", "alpha"], "sess-2", self.other_dir)
        leader = _leader(self._conn(), "alpha", 2)
        self.assertEqual(leader["cwd"], str(self.other_dir.resolve()))
        self.assertEqual(_leader(self._conn(), "alpha", 1)["cwd"], str(self.repo_dir.resolve()))

    def test_human_resume_by_session_name_does_not_locate(self):
        self.run_cli(["handoff", "--in-flight", "x", "--learned", "y"], "sess-1", self.repo_dir)
        (self.sessions_dir / "1.json").write_text('{"sessionId": "sess-3", "name": "leader-three"}')
        code, out, err = self.run_cli(
            ["party", "resume", "alpha", "--session", "leader-three"], None, self.other_dir
        )
        self.assertEqual(code, 0, err)
        self.assertIsNone(_leader(self._conn(), "alpha", 2)["cwd"])

    def test_auto_resume_locates_with_hook_cwd_and_mode(self):
        self.run_cli(["handoff", "--in-flight", "x", "--learned", "y"], "sess-1", self.repo_dir)
        with mock.patch.dict(os.environ, {"GUILD_RESUME": "alpha"}):
            self.run_hook(
                "session-start",
                {"session_id": "sess-2", "cwd": str(self.other_dir), "permission_mode": "plan"},
            )
        leader = _leader(self._conn(), "alpha", 2)
        self.assertEqual(leader["cwd"], str(self.other_dir))
        self.assertEqual(leader["permission_mode"], "plan")


class LeaderLocationProjectionTests(GuildTestCase):
    def test_rebuild_replays_location(self):
        repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha"], "sess-1", repo_dir)
        self.run_hook(
            "session-start", {"session_id": "sess-1", "cwd": str(self.root), "permission_mode": "plan"}
        )
        before = dict(_leader(db.connect(paths.db_path()), "alpha", 1))
        code, out, err = self.run_cli(["rebuild"], None, None)
        self.assertEqual(code, 0, err)
        after = dict(_leader(db.connect(paths.db_path()), "alpha", 1))
        self.assertEqual(before, after)
        self.assertEqual(after["cwd"], str(self.root))
        self.assertEqual(after["permission_mode"], "plan")

    def test_export_skips_local_location_events(self):
        repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha"], "sess-1", repo_dir)
        code, out, err = self.run_cli(["export", "--visibility", "guild"], None, None)
        self.assertNotIn("leader.located", out)

    def test_old_schema_db_gains_leader_location_columns(self):
        db_path = self.data_home / "guild.db"
        _make_old_schema_db(db_path)
        conn = db.connect(db_path)
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(leaders)").fetchall()}
        self.assertTrue({"cwd", "permission_mode"} <= columns)
        leader = conn.execute("SELECT * FROM leaders WHERE party = 'alpha'").fetchone()
        self.assertIsNone(leader["cwd"])
        self.assertIsNone(leader["permission_mode"])
