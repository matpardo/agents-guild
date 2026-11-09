import os
from unittest import mock

from guild import db, events, paths, timeutil
from tests.testutil import GuildTestCase


class HandoffConsumedTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(
            ["party", "start", "alpha", "--reason", "test reason", "--goal", "test goal", "--done-when", "test done"],
            "sess-1",
            self.repo_dir,
        )
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", self.repo_dir)
        self.run_cli(
            ["task", "add", "demo/T01", "--title", "First", "--reason", "serves the goal"], "sess-1", self.repo_dir
        )
        self.run_cli(["handoff", "--in-flight", "x", "--learned", "y"], "sess-1", self.repo_dir)

    def _conn(self):
        return db.connect(paths.db_path())

    def _leader(self, generation):
        return (
            self._conn()
            .execute("SELECT * FROM leaders WHERE party = 'alpha' AND generation = ?", (generation,))
            .fetchone()
        )

    def test_handed_off_generation_is_not_consumed_before_resume(self):
        self.assertIsNotNone(self._leader(1)["handoff_path"])
        self.assertIsNone(self._leader(1)["handoff_consumed_at"])

    def test_manual_party_resume_consumes_previous_generation_only(self):
        self.run_cli(["party", "resume", "alpha"], "sess-2", self.repo_dir)
        self.assertIsNotNone(self._leader(1)["handoff_consumed_at"])
        self.assertIsNone(self._leader(2)["handoff_consumed_at"])

    def test_hook_auto_resume_consumes_previous_generation(self):
        with mock.patch.dict(os.environ, {"GUILD_RESUME": "alpha"}):
            self.run_hook("session-start", {"session_id": "sess-2", "cwd": str(self.repo_dir)})
        self.assertIsNotNone(self._leader(1)["handoff_consumed_at"])

    def test_refused_resume_consumes_nothing(self):
        self.run_cli(["party", "close", "alpha", "--force", "--pending", "none"], None, None)
        code, out, err = self.run_cli(["party", "resume", "alpha"], "sess-2", self.repo_dir)
        self.assertEqual(code, 1)
        self.assertIsNone(self._leader(1)["handoff_consumed_at"])

    def test_rebuild_reproduces_consumed(self):
        self.run_cli(["party", "resume", "alpha"], "sess-2", self.repo_dir)
        before = self._leader(1)["handoff_consumed_at"]
        self.run_cli(["rebuild"], None, None)
        self.assertEqual(self._leader(1)["handoff_consumed_at"], before)
        self.assertIsNone(self._leader(2)["handoff_consumed_at"])

    def test_pruned_event_nulls_path_and_survives_rebuild(self):
        conn = self._conn()
        path = self._leader(1)["handoff_path"]
        with db.writing(conn):
            events.record(
                conn,
                timeutil.utcnow(),
                "tester@host",
                "alpha",
                None,
                "acme",
                "handoff.pruned",
                "local",
                {"party": "alpha", "generation": 1, "path": path},
            )
        self.assertIsNone(self._leader(1)["handoff_path"])
        self.run_cli(["rebuild"], None, None)
        self.assertIsNone(self._leader(1)["handoff_path"])
