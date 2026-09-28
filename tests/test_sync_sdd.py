import json

from tests.testutil import GuildTestCase

_PATTERNS = {
    "task_heading": r"^#{2,3}\s+(T\d+\w*)\s+.*[-—]\s*(.+)$",
    "key_ref": r"[A-Z]{2,10}-\d+",
    "deps_line": r"^\*\*Deps:\*\*\s*(.+)$",
    "status_line": r"^\*\*Status:\*\*\s*(.+)$",
}


class SyncSddTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.project_root = self.root / "projects" / "acme"
        self.repo_dir = self.project_root / "repo"
        self.repo_dir.mkdir(parents=True)
        self.sdd_root = self.project_root / "sdd-docs"
        (self.sdd_root / "epics" / "widget-rollout").mkdir(parents=True)
        (self.sdd_root / "epics" / "widget-rollout" / "tasks.md").write_text(
            "## T01 — Configure retries\n\n**Deps:** —\n\n**Status:** [x] done\n\n"
            "## T02 — Add validation\n\n**Deps:** T01\n\n**Status:** [ ] pending\n"
        )
        self._write_project_config()
        self.run_cli(["party", "start", "alpha"], "sess-1", self.repo_dir)

    def _write_project_config(self, sdd_config=None):
        projects_dir = self.config_home / "guild" / "projects"
        projects_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "name": "acme",
            "paths": [str(self.project_root) + "/*"],
            "github": {"repos": ["acme/app"]},
        }
        if sdd_config is not None:
            data["sdd"] = sdd_config
        (projects_dir / "acme.json").write_text(json.dumps(data))

    def test_sync_without_sdd_config_fails_clearly(self):
        self._write_project_config(sdd_config=None)
        code, out, err = self.run_cli(["sync", "--source", "sdd"], "sess-1", self.repo_dir)
        self.assertEqual(code, 1)
        self.assertIn("no 'sdd' config block", err)

    def test_sync_parses_epic_and_populates_tasks(self):
        self._write_project_config(
            sdd_config=dict(_PATTERNS, root=str(self.sdd_root), epics_dir="epics")
        )
        code, out, err = self.run_cli(["sync", "--source", "sdd"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0)
        code, out, err = self.run_cli(
            [
                "quest", "add", "wave1", "--title", "Wave 1", "--epic", "widget-rollout",
                "--tasks", "T01,T02",
            ],
            "sess-1", self.repo_dir,
        )
        self.assertEqual(code, 0)
        code, out, err = self.run_cli(["board"], "sess-1", self.repo_dir)
        self.assertIn("queued: T01, T02", out)

    def test_sync_reports_unparseable_file_and_exits_nonzero(self):
        (self.sdd_root / "epics" / "letters").mkdir(parents=True)
        (self.sdd_root / "epics" / "letters" / "tasks.md").write_text("## A1 — no match\n")
        self._write_project_config(
            sdd_config=dict(_PATTERNS, root=str(self.sdd_root), epics_dir="epics")
        )
        code, out, err = self.run_cli(["sync", "--source", "sdd"], "sess-1", self.repo_dir)
        self.assertEqual(code, 1)
        self.assertIn("letters", err)
        self.assertIn("no matching task headings", err)

    def test_sync_continues_other_epics_after_one_failure(self):
        (self.sdd_root / "epics" / "letters").mkdir(parents=True)
        (self.sdd_root / "epics" / "letters" / "tasks.md").write_text("## A1 — no match\n")
        self._write_project_config(
            sdd_config=dict(_PATTERNS, root=str(self.sdd_root), epics_dir="epics")
        )
        self.run_cli(["sync", "--source", "sdd"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(
            [
                "quest", "add", "wave1", "--title", "Wave 1", "--epic", "widget-rollout",
                "--tasks", "T01",
            ],
            "sess-1", self.repo_dir,
        )
        self.assertEqual(code, 0)

    def test_rebuild_is_idempotent_for_epic_tasks(self):
        self._write_project_config(
            sdd_config=dict(_PATTERNS, root=str(self.sdd_root), epics_dir="epics")
        )
        self.run_cli(["sync", "--source", "sdd"], "sess-1", self.repo_dir)
        self.run_cli(["sync", "--source", "sdd"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["rebuild"], None, self.root)
        self.assertEqual(code, 0)


if __name__ == "__main__":
    import unittest

    unittest.main()
