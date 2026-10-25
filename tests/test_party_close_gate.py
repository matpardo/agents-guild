from tests.test_drift import DriftTestCase

_DRIFT_EPIC = "## T01 — First\n\n**Deps:** —\n**Status:** [ ] pending\n"


class PartyCloseGateTests(DriftTestCase):
    def setUp(self):
        super().setUp()
        self._write_epic("wave1", "status: active\n", _DRIFT_EPIC)
        self._sync_sdd()
        self.run_cli(
            ["quest", "add", "wave1-q", "--title", "Wave", "--epic", "wave1", "--tasks", "T01"],
            "sess-1",
            self.repo_dir,
        )
        self._track_pr(1, "wave1-q", "T01")
        self._set_pr_lifecycle(1, "merged")
        self.run_cli(["task", "done", "wave1-q/T01", "--summary", "shipped"], "sess-1", self.repo_dir)

    def _quest_state(self):
        return self.conn.execute("SELECT state FROM quests WHERE slug = 'wave1-q'").fetchone()["state"]

    def _party_state(self):
        return self.conn.execute("SELECT state FROM parties WHERE name = 'alpha'").fetchone()["state"]

    def test_close_refuses_when_quest_has_drift(self):
        code, out, err = self.run_cli(["party", "close", "alpha", "--pending", "none"], None, None)
        self.assertEqual(code, 1)
        self.assertIn("quest 'wave1-q'", err)
        self.assertIn("drift in epic 'wave1'", err)
        self.assertIn("--force", err)
        self.assertEqual(self._quest_state(), "active")
        self.assertNotEqual(self._party_state(), "closed")

    def test_close_refuses_when_quest_has_unfinished_tasks(self):
        self.run_cli(["quest", "add", "loose", "--title", "Loose", "--no-epic"], "sess-1", self.repo_dir)
        self.run_cli(["task", "add", "loose/T01", "--title", "Open"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["party", "close", "alpha", "--pending", "none"], None, None)
        self.assertEqual(code, 1)
        self.assertIn("quest 'loose' has tasks not done", err)
        self.assertIn("T01 (queued)", err)

    def test_force_closes_and_reports_unfinished_work_per_quest(self):
        code, out, err = self.run_cli(["party", "close", "alpha", "--force", "--pending", "none"], None, None)
        self.assertEqual(code, 0, err)
        self.assertIn("closed with unfinished work: quest 'wave1-q' has drift in epic 'wave1'", out)
        self.assertEqual(self._quest_state(), "done")
        self.assertEqual(self._party_state(), "closed")
