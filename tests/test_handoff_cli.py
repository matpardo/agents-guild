import os
import sqlite3

from guild import locking, paths
from tests.testutil import GuildTestCase

_DEAD = "11111111-1111-4111-8111-111111111111"


class HandoffCliTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(
            ["party", "start", "alpha", "--reason", "test reason", "--goal", "test goal", "--done-when", "test done"],
            "sess-1",
            self.repo_dir,
        )
        self.run_cli(["handoff", "--in-flight", "x", "--learned", "y"], "sess-1", self.repo_dir)
        self.run_cli(["party", "resume", "alpha"], "sess-2", self.repo_dir)
        self.run_cli(["handoff", "--in-flight", "x", "--learned", "y"], "sess-2", self.repo_dir)
        self.first = paths.handoffs_dir() / "alpha-g1.md"

    def _pruned_count(self):
        conn = sqlite3.connect(str(paths.db_path()))
        count = conn.execute("SELECT COUNT(*) FROM events WHERE kind = 'handoff.pruned'").fetchone()[0]
        conn.close()
        return count

    def test_missing_in_flight_is_a_guild_error(self):
        code, out, err = self.run_cli(["handoff", "--learned", "y"], "sess-2", self.repo_dir)
        self.assertEqual(code, 1)
        self.assertIn("--in-flight", err)

    def test_missing_learned_is_a_guild_error(self):
        code, out, err = self.run_cli(["handoff", "--in-flight", "x"], "sess-2", self.repo_dir)
        self.assertEqual(code, 1)
        self.assertIn("--learned", err)

    def test_prune_deletes_superseded_consumed_handoff(self):
        code, out, err = self.run_cli(["handoff", "prune"], None, None)
        self.assertEqual(code, 0, err)
        self.assertIn("handoff prune: 1 handoffs, 0 markers", out)
        self.assertIn("delete handoff alpha-g1.md: superseded and consumed", out)
        self.assertFalse(self.first.exists())

    def test_prune_dry_run_changes_nothing(self):
        code, out, err = self.run_cli(["handoff", "prune", "--dry-run"], None, None)
        self.assertEqual(code, 0, err)
        self.assertIn("handoff prune (dry-run): 1 handoffs, 0 markers", out)
        self.assertIn("would delete handoff alpha-g1.md: superseded and consumed", out)
        self.assertTrue(self.first.exists())
        self.assertEqual(self._pruned_count(), 0)

    def test_prune_rejects_other_flags(self):
        for extra in (["--in-flight", "x"], ["--learned", "y"], ["--model", "m"]):
            with self.subTest(extra=extra):
                code, out, err = self.run_cli(["handoff", "prune", *extra], None, None)
                self.assertEqual(code, 1)
                self.assertIn("prune", err)
        self.assertTrue(self.first.exists())

    def test_dry_run_without_prune_is_rejected(self):
        code, out, err = self.run_cli(
            ["handoff", "--in-flight", "x", "--learned", "y", "--dry-run"], "sess-2", self.repo_dir
        )
        self.assertEqual(code, 1)
        self.assertIn("--dry-run", err)

    def test_unknown_action_is_rejected_by_parser(self):
        code, out, err = self.run_cli(["handoff", "wipe"], None, None)
        self.assertEqual(code, 2)

    def test_prune_removes_dead_markers_when_registry_exists(self):
        (self.sessions_dir / "live.json").write_text('{"sessionId": "22222222-2222-4222-8222-222222222222"}')
        marker = paths.state_dir() / "ctx" / _DEAD
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("1")
        stamp = os.path.getmtime(str(marker)) - 2 * 86400
        os.utime(str(marker), (stamp, stamp))
        code, out, err = self.run_cli(["handoff", "prune"], None, None)
        self.assertIn("delete marker ctx/{}: session not running".format(_DEAD), out)
        self.assertFalse(marker.exists())

    def test_prune_reports_already_running_when_locked(self):
        with locking.try_lock(paths.state_dir() / "handoff-prune", "prune.lock") as acquired:
            self.assertTrue(acquired)
            code, out, err = self.run_cli(["handoff", "prune"], None, None)
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "prune already running")
        self.assertTrue(self.first.exists())
