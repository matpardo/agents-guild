import sqlite3

from guild import paths
from tests.testutil import GuildTestCase


class PartyParkTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(
            ["party", "start", "alpha", "--reason", "test reason", "--goal", "test goal", "--done-when", "test done"],
            "sess-1",
            self.repo_dir,
        )

    def _parked(self):
        conn = sqlite3.connect(str(paths.db_path()))
        row = conn.execute("SELECT parked, parked_at FROM parties WHERE name = 'alpha'").fetchone()
        conn.close()
        return row

    def _handoff(self, extra):
        return self.run_cli(["handoff", "--in-flight", "x", "--learned", "y"] + extra, "sess-1", self.repo_dir)

    def test_handoff_parked_is_stored_trimmed(self):
        code, out, err = self._handoff(["--parked", "  legal answer "])
        self.assertEqual(code, 0, err)
        self.assertEqual(self._parked()[0], "legal answer")
        self.assertIsNotNone(self._parked()[1])

    def test_handoff_blank_parked_is_refused(self):
        code, out, err = self._handoff(["--parked", "  "])
        self.assertEqual(code, 1)
        self.assertIn("--parked must not be empty", err)
        self.assertIsNone(self._parked()[0])

    def test_handoff_parked_with_party_is_refused(self):
        code, out, err = self.run_cli(["handoff", "--party", "alpha", "--parked", "x"], None, None)
        self.assertEqual(code, 1)
        self.assertIn("--party cannot be combined with --parked", err)

    def test_handoff_parked_with_prune_is_refused(self):
        code, out, err = self.run_cli(["handoff", "prune", "--parked", "x"], None, None)
        self.assertEqual(code, 1)
        self.assertIn("handoff prune does not take --parked", err)

    def test_handoff_parked_rejects_an_email(self):
        code, out, err = self._handoff(["--parked", "mail a@b.com"])
        self.assertEqual(code, 1)
        self.assertIsNone(self._parked()[0])

    def test_park_and_unpark(self):
        code, out, err = self.run_cli(["party", "park", "alpha", "--reason", "vendor"], None, None)
        self.assertEqual(code, 0, err)
        self.assertEqual(self._parked()[0], "vendor")
        code, out, err = self.run_cli(["party", "unpark", "alpha"], None, None)
        self.assertEqual(code, 0, err)
        self.assertEqual(self._parked(), (None, None))

    def test_park_blank_reason_is_refused(self):
        code, out, err = self.run_cli(["party", "park", "alpha", "--reason", " "], None, None)
        self.assertEqual(code, 1)
        self.assertIsNone(self._parked()[0])

    def test_park_unknown_party_is_refused(self):
        code, out, err = self.run_cli(["party", "park", "ghost", "--reason", "x"], None, None)
        self.assertEqual(code, 1)
        self.assertIn("unknown party", err)

    def test_park_closed_party_is_refused(self):
        self.run_cli(["party", "close", "--pending", "none"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["party", "park", "alpha", "--reason", "x"], None, None)
        self.assertEqual(code, 1)
        self.assertIn("is closed", err)

    def test_unpark_when_not_parked_is_refused(self):
        code, out, err = self.run_cli(["party", "unpark", "alpha"], None, None)
        self.assertEqual(code, 1)
        self.assertIn("is not parked", err)

    def test_rebuild_replays_park_and_unpark(self):
        self.run_cli(["party", "park", "alpha", "--reason", "vendor"], None, None)
        self.run_cli(["rebuild"], None, None)
        self.assertEqual(self._parked()[0], "vendor")
        self.run_cli(["party", "unpark", "alpha"], None, None)
        self.run_cli(["rebuild"], None, None)
        self.assertEqual(self._parked(), (None, None))

    def test_rebuild_replays_handoff_parked_then_resume_clears(self):
        self._handoff(["--parked", "legal"])
        self.run_cli(["rebuild"], None, None)
        self.assertEqual(self._parked()[0], "legal")
        self.run_cli(["party", "resume", "alpha"], "sess-2", self.repo_dir)
        self.run_cli(["rebuild"], None, None)
        self.assertEqual(self._parked(), (None, None))

    def test_board_status_line_shows_reason(self):
        self.run_cli(["party", "park", "alpha", "--reason", "vendor"], None, None)
        code, out, err = self.run_cli(["board"], None, None)
        self.assertIn("status: parked", out)
        self.assertIn("— vendor", out)
