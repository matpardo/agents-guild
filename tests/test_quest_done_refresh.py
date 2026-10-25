import shutil

from tests.test_quest_done_achievement import QuestDoneTestCase

_PENDING_EPIC = (
    "## T01 — First\n\n**JIRA:** DEMO-21\n**Deps:** —\n**Status:** [ ] pending\n\n"
    "## T02 — Second\n\n**JIRA:** DEMO-22\n**Deps:** —\n**Status:** [ ] pending\n"
)
_DONE_EPIC = _PENDING_EPIC.replace("[ ] pending\n\n## T02", "[x] done\n\n## T02")


class QuestDoneRefreshTests(QuestDoneTestCase):
    def setUp(self):
        super().setUp()
        self._write_epic("wave4", "jira: DEMO-20\nstatus: active\n", _PENDING_EPIC)
        self._sync_sdd()
        self._record_cards(
            [
                self._card("DEMO-21", "done", parent_key="DEMO-20"),
                self._card("DEMO-22", "new", parent_key="DEMO-20"),
            ]
        )
        self._add_quest("wave4-q", "wave4", "T01")
        self.run_cli(["task", "done", "wave4-q/T01", "--summary", "shipped"], "sess-1", self.repo_dir)

    def _synced_count(self):
        return self.conn.execute("SELECT COUNT(*) AS n FROM events WHERE kind = 'epic.synced'").fetchone()["n"]

    def test_stale_snapshot_is_refreshed_before_the_gate(self):
        self._write_epic("wave4", "jira: DEMO-20\nstatus: active\n", _DONE_EPIC)
        code, out, err = self.run_cli(["quest", "done", "wave4-q"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        self.assertEqual(self._quest_state("wave4-q"), "done")

    def test_refresh_failure_keeps_stored_snapshot_and_hints_stale(self):
        shutil.rmtree(str(self.sdd_root))
        code, out, err = self.run_cli(["quest", "done", "wave4-q"], "sess-1", self.repo_dir)
        self.assertEqual(code, 1)
        self.assertIn("tracker=done (done), sdd=pending", err)
        self.assertIn("sdd snapshot may be stale", err)
        self.assertIn("guild sync --source sdd", err)

    def test_party_close_refreshes_once(self):
        self._add_quest("wave4-r", "wave4", "T02")
        self.run_cli(["task", "done", "wave4-r/T02", "--summary", "shipped"], "sess-1", self.repo_dir)
        self._write_epic("wave4", "jira: DEMO-20\nstatus: active\n", _DONE_EPIC)
        before = self._synced_count()
        self.run_cli(["party", "close", "alpha", "--pending", "none"], None, None)
        self.assertEqual(self._synced_count(), before + 1)
