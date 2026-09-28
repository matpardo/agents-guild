import json
import sqlite3

from tests.testutil import GuildTestCase

_SDD_PATTERNS = {
    "task_heading": r"^#{2,3}\s+(T\d+\w*)\b.*?\s[—–-]\s+(.+)$",
    "key_ref": r"[A-Z][A-Z0-9]*-\d+",
    "deps_line": r"^\*\*Deps:\*\*\s*(.+)$",
    "status_line": r"^\*\*Status:\*\*\s*(.+)$",
    "key_line": r"^\*\*JIRA:\*\*\s*(.+)$",
    "epic_key_field": "jira",
}


class SyncTrackerTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.project_root = self.root / "projects" / "acme"
        self.repo_dir = self.project_root / "repo"
        self.repo_dir.mkdir(parents=True)
        self.sdd_root = self.project_root / "sdd-docs"
        self._write_project_config()
        self.run_cli(["party", "start", "alpha"], "sess-1", self.repo_dir)

    def _write_project_config(self, tracker_config=None, sdd_config=None):
        projects_dir = self.config_home / "guild" / "projects"
        projects_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "name": "acme",
            "paths": [str(self.project_root) + "/*"],
            "github": {"repos": ["acme/app"]},
        }
        if tracker_config is not None:
            data["tracker"] = tracker_config
        if sdd_config is not None:
            data["sdd"] = sdd_config
        (projects_dir / "acme.json").write_text(json.dumps(data))

    def _write_epic(self, tasks_md_text):
        epic_dir = self.sdd_root / "epics" / "widget-rollout"
        epic_dir.mkdir(parents=True, exist_ok=True)
        (epic_dir / "tasks.md").write_text(tasks_md_text)

    def _sync_sdd(self):
        code, out, err = self.run_cli(["sync", "--source", "sdd"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)

    def _sync_tracker(self):
        return self.run_cli(["sync", "--source", "tracker"], "sess-1", self.repo_dir)

    def _cards(self):
        conn = sqlite3.connect(str(self.data_home / "guild" / "guild.db"))
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM cards WHERE project = 'acme' ORDER BY key").fetchall()
        conn.close()
        return {row["key"]: dict(row) for row in rows}

    def test_sync_without_tracker_config_fails_clearly(self):
        code, out, err = self._sync_tracker()
        self.assertEqual(code, 1)
        self.assertIn("no 'tracker' config block", err)

    def test_sync_rejects_unsupported_tracker_kind(self):
        self._write_project_config(tracker_config={"kind": "other"})
        code, out, err = self._sync_tracker()
        self.assertEqual(code, 1)
        self.assertIn("not supported", err)

    def test_sync_rejects_missing_kind(self):
        self._write_project_config(tracker_config={})
        code, out, err = self._sync_tracker()
        self.assertEqual(code, 1)
        self.assertIn("not supported", err)

    def test_children_of_epic_and_standalone_task_and_epic_itself(self):
        self._write_project_config(
            tracker_config={"kind": "jira-acli"},
            sdd_config=dict(_SDD_PATTERNS, root=str(self.sdd_root), epics_dir="epics"),
        )
        self._write_epic(
            "---\nepic: widget-rollout\njira: DEMO-1\n---\n\n"
            "## T01 — Configure retries\n\n**JIRA:** DEMO-2\n**Deps:** —\n**Status:** [ ] pending\n\n"
            "## T02 — Standalone\n\n**JIRA:** DEMO-9\n**Deps:** —\n**Status:** [ ] pending\n"
        )
        self._sync_sdd()
        self.write_acli_fixture(
            "parent = DEMO-1",
            [{"key": "DEMO-2", "fields": {"status": {"name": "In Progress", "statusCategory": {"key": "indeterminate"}}, "issuetype": {"name": "Task"}}}],
        )
        self.write_acli_fixture(
            "key in (DEMO-1,DEMO-9)",
            [
                {"key": "DEMO-1", "fields": {"status": {"name": "In Progress", "statusCategory": {"key": "indeterminate"}}, "issuetype": {"name": "Epic"}}},
                {"key": "DEMO-9", "fields": {"status": {"name": "Done", "statusCategory": {"key": "done"}}, "issuetype": {"name": "Task"}}},
            ],
        )
        code, out, err = self._sync_tracker()
        self.assertEqual(code, 0, err)
        cards = self._cards()
        self.assertEqual(cards["DEMO-2"]["parent_key"], "DEMO-1")
        self.assertIsNone(cards["DEMO-1"]["parent_key"])
        self.assertIsNone(cards["DEMO-9"]["parent_key"])
        self.assertEqual(cards["DEMO-9"]["status_category"], "done")

    def test_missing_key_is_reported_and_exit_nonzero(self):
        self._write_project_config(
            tracker_config={"kind": "jira-acli"},
            sdd_config=dict(_SDD_PATTERNS, root=str(self.sdd_root), epics_dir="epics"),
        )
        self._write_epic(
            "## T01 — Gone\n\n**JIRA:** DEMO-404\n**Deps:** —\n**Status:** [ ] pending\n"
        )
        self._sync_sdd()
        self.write_acli_fixture("key in (DEMO-404)", [])
        code, out, err = self._sync_tracker()
        self.assertEqual(code, 1)
        self.assertIn("DEMO-404: not found in tracker", err)

    def test_invalid_key_is_reported_and_skipped(self):
        self._write_project_config(
            tracker_config={"kind": "jira-acli"},
            sdd_config=dict(_SDD_PATTERNS, root=str(self.sdd_root), epics_dir="epics", key_ref=r"[A-Z]-\d+"),
        )
        self._write_epic(
            "## T01 — Bad key\n\n**JIRA:** A-1\n**Deps:** —\n**Status:** [ ] pending\n"
        )
        self._sync_sdd()
        code, out, err = self._sync_tracker()
        self.assertEqual(code, 1)
        self.assertIn("A-1: invalid tracker key", err)

    def test_rebuild_is_idempotent_for_cards(self):
        self._write_project_config(
            tracker_config={"kind": "jira-acli"},
            sdd_config=dict(_SDD_PATTERNS, root=str(self.sdd_root), epics_dir="epics"),
        )
        self._write_epic(
            "---\nepic: widget-rollout\njira: DEMO-1\n---\n\n"
            "## T01 — Configure retries\n\n**JIRA:** DEMO-2\n**Deps:** —\n**Status:** [ ] pending\n"
        )
        self._sync_sdd()
        self.write_acli_fixture(
            "parent = DEMO-1",
            [{"key": "DEMO-2", "fields": {"status": {"name": "To Do", "statusCategory": {"key": "new"}}, "issuetype": {"name": "Task"}}}],
        )
        self.write_acli_fixture("key in (DEMO-1)", [{"key": "DEMO-1", "fields": {"status": {"name": "Open", "statusCategory": {"key": "new"}}, "issuetype": {"name": "Epic"}}}])
        self._sync_tracker()
        self._sync_tracker()
        code, out, err = self.run_cli(["rebuild"], None, self.root)
        self.assertEqual(code, 0)
        self.assertEqual(len(self._cards()), 2)


if __name__ == "__main__":
    import unittest

    unittest.main()
