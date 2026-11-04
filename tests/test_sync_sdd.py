import json
import sqlite3
import subprocess

from guild import db, paths, reducers
from tests.testutil import GuildTestCase

_PATTERNS = {
    "task_heading": r"^#{2,3}\s+(T\d+\w*)\b.*?\s[—–-]\s+(.+)$",
    "key_ref": r"[A-Z]{2,10}-\d+",
    "deps_line": r"^\*\*Deps:\*\*\s*(.+)$",
    "status_line": r"^\*\*Status:\*\*\s*(.+)$",
}


def _git(args, cwd):
    result = subprocess.run(["git"] + args, cwd=str(cwd), capture_output=True, text=True)
    if result.returncode != 0:
        raise AssertionError("git {} failed: {}".format(args, result.stderr))
    return result.stdout


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
        self.run_cli(["party", "start", "alpha", "--reason", "test reason"], "sess-1", self.repo_dir)

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
        self._write_project_config(sdd_config=dict(_PATTERNS, root=str(self.sdd_root), epics_dir="epics"))
        code, out, err = self.run_cli(["sync", "--source", "sdd"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0)
        code, out, err = self.run_cli(
            [
                "quest",
                "add",
                "wave1",
                "--title",
                "Wave 1",
                "--epic",
                "widget-rollout",
                "--tasks",
                "T01,T02",
            ],
            "sess-1",
            self.repo_dir,
        )
        self.assertEqual(code, 0)
        code, out, err = self.run_cli(["board"], "sess-1", self.repo_dir)
        self.assertIn("queued: T01, T02", out)

    def test_nested_epics_dir_under_root_syncs(self):
        nested = self.sdd_root / "docs" / "specs" / "epics" / "inner-epic"
        nested.mkdir(parents=True)
        (nested / "tasks.md").write_text("## T01 — Nested task\n\n**Deps:** —\n\n**Status:** [ ] pending\n")
        self._write_project_config(sdd_config=dict(_PATTERNS, root=str(self.sdd_root), epics_dir="docs/specs/epics"))
        code, out, err = self.run_cli(["sync", "--source", "sdd"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        conn = sqlite3.connect(str(self.data_home / "guild" / "guild.db"))
        rows = conn.execute("SELECT epic FROM epics").fetchall()
        conn.close()
        self.assertEqual(rows, [("inner-epic",)])

    def test_sync_stores_key_from_configured_key_line(self):
        (self.sdd_root / "epics" / "widget-rollout" / "tasks.md").write_text(
            "## T01 — Configure retries\n\n**JIRA:** DEMO-12\n**Deps:** —\n**Status:** [ ] pending\n"
        )
        self._write_project_config(
            sdd_config=dict(_PATTERNS, root=str(self.sdd_root), epics_dir="epics", key_line=r"^\*\*JIRA:\*\*\s*(.+)$")
        )
        code, out, err = self.run_cli(["sync", "--source", "sdd"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        conn = sqlite3.connect(str(self.data_home / "guild" / "guild.db"))
        row = conn.execute("SELECT jira_key FROM tasks WHERE tid = 'T01'").fetchone()
        conn.close()
        self.assertEqual(row[0], "DEMO-12")

    def test_sync_stores_epic_key_from_configured_frontmatter_field(self):
        (self.sdd_root / "epics" / "widget-rollout" / "tasks.md").write_text(
            "---\nepic: widget-rollout\njira: DEMO-1\n---\n\n"
            "## T01 — Configure retries\n\n**Deps:** —\n**Status:** [ ] pending\n"
        )
        self._write_project_config(
            sdd_config=dict(_PATTERNS, root=str(self.sdd_root), epics_dir="epics", epic_key_field="jira")
        )
        code, out, err = self.run_cli(["sync", "--source", "sdd"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        conn = sqlite3.connect(str(self.data_home / "guild" / "guild.db"))
        row = conn.execute("SELECT jira_key FROM epics WHERE epic = 'widget-rollout'").fetchone()
        conn.close()
        self.assertEqual(row[0], "DEMO-1")

    def test_sync_gives_no_epic_key_when_field_not_configured(self):
        self._write_project_config(sdd_config=dict(_PATTERNS, root=str(self.sdd_root), epics_dir="epics"))
        code, out, err = self.run_cli(["sync", "--source", "sdd"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        conn = sqlite3.connect(str(self.data_home / "guild" / "guild.db"))
        row = conn.execute("SELECT jira_key FROM epics WHERE epic = 'widget-rollout'").fetchone()
        conn.close()
        self.assertIsNone(row[0])

    def test_sync_stores_epic_status_from_configured_frontmatter_field(self):
        (self.sdd_root / "epics" / "widget-rollout" / "tasks.md").write_text(
            "---\nepic: widget-rollout\nstatus: done\n---\n\n"
            "## T01 — Configure retries\n\n**Deps:** —\n**Status:** [ ] pending\n"
        )
        self._write_project_config(
            sdd_config=dict(_PATTERNS, root=str(self.sdd_root), epics_dir="epics", epic_status_field="status")
        )
        code, out, err = self.run_cli(["sync", "--source", "sdd"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        conn = sqlite3.connect(str(self.data_home / "guild" / "guild.db"))
        row = conn.execute("SELECT sdd_status FROM epics WHERE epic = 'widget-rollout'").fetchone()
        conn.close()
        self.assertEqual(row[0], "done")

    def test_sync_gives_no_epic_status_when_field_not_configured(self):
        self._write_project_config(sdd_config=dict(_PATTERNS, root=str(self.sdd_root), epics_dir="epics"))
        code, out, err = self.run_cli(["sync", "--source", "sdd"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        conn = sqlite3.connect(str(self.data_home / "guild" / "guild.db"))
        row = conn.execute("SELECT sdd_status FROM epics WHERE epic = 'widget-rollout'").fetchone()
        conn.close()
        self.assertIsNone(row[0])

    def test_legacy_epic_synced_event_without_jira_key_replays_as_none(self):
        legacy_event = {
            "ts": "2026-01-01T00:00:00+00:00",
            "project": "acme",
            "payload": {"project": "acme", "epic": "widget-rollout", "sdd_path": "x", "tasks": []},
        }
        conn = db.connect(paths.db_path())
        reducers.apply(conn, dict(legacy_event, kind="epic.synced"))
        row = conn.execute("SELECT jira_key, sdd_status FROM epics WHERE epic = 'widget-rollout'").fetchone()
        conn.close()
        self.assertIsNone(row["jira_key"])
        self.assertIsNone(row["sdd_status"])

    def test_missing_sdd_root_fails_instead_of_syncing_nothing(self):
        self._write_project_config(sdd_config=dict(_PATTERNS, root=str(self.project_root / "gone"), epics_dir="epics"))
        code, out, err = self.run_cli(["sync", "--source", "sdd"], "sess-1", self.repo_dir)
        self.assertEqual(code, 1)
        self.assertIn("does not exist", err)

    def test_sync_reports_unparseable_file_and_exits_nonzero(self):
        (self.sdd_root / "epics" / "letters").mkdir(parents=True)
        (self.sdd_root / "epics" / "letters" / "tasks.md").write_text("## A1 — no match\n")
        self._write_project_config(sdd_config=dict(_PATTERNS, root=str(self.sdd_root), epics_dir="epics"))
        code, out, err = self.run_cli(["sync", "--source", "sdd"], "sess-1", self.repo_dir)
        self.assertEqual(code, 1)
        self.assertIn("letters", err)
        self.assertIn("no matching task headings", err)

    def test_sync_continues_other_epics_after_one_failure(self):
        (self.sdd_root / "epics" / "letters").mkdir(parents=True)
        (self.sdd_root / "epics" / "letters" / "tasks.md").write_text("## A1 — no match\n")
        self._write_project_config(sdd_config=dict(_PATTERNS, root=str(self.sdd_root), epics_dir="epics"))
        self.run_cli(["sync", "--source", "sdd"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(
            [
                "quest",
                "add",
                "wave1",
                "--title",
                "Wave 1",
                "--epic",
                "widget-rollout",
                "--tasks",
                "T01",
            ],
            "sess-1",
            self.repo_dir,
        )
        self.assertEqual(code, 0)

    def test_duplicate_task_ids_fail_the_epic_and_the_others_still_sync(self):
        (self.sdd_root / "epics" / "dupes").mkdir(parents=True)
        (self.sdd_root / "epics" / "dupes" / "tasks.md").write_text("## T01 — one\n\n## T01 — one again\n")
        self._write_project_config(sdd_config=dict(_PATTERNS, root=str(self.sdd_root), epics_dir="epics"))
        code, out, err = self.run_cli(["sync", "--source", "sdd"], "sess-1", self.repo_dir)
        self.assertEqual(code, 1)
        self.assertIn("dupes", err)
        self.assertIn("duplicate task ids: T01", err)
        self.assertNotIn("Traceback", err)
        code, out, err = self.run_cli(
            ["quest", "add", "wave1", "--title", "Wave 1", "--epic", "widget-rollout", "--tasks", "T01"],
            "sess-1",
            self.repo_dir,
        )
        self.assertEqual(code, 0, err)

    def test_rebuild_is_idempotent_for_epic_tasks(self):
        self._write_project_config(sdd_config=dict(_PATTERNS, root=str(self.sdd_root), epics_dir="epics"))
        self.run_cli(["sync", "--source", "sdd"], "sess-1", self.repo_dir)
        self.run_cli(["sync", "--source", "sdd"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["rebuild"], None, self.root)
        self.assertEqual(code, 0)

    def test_sdd_config_cannot_combine_root_and_git(self):
        self._write_project_config(
            sdd_config=dict(
                _PATTERNS,
                root=str(self.sdd_root),
                epics_dir="epics",
                git_repo=str(self.sdd_root),
                git_ref="origin/main",
            )
        )
        code, out, err = self.run_cli(["sync", "--source", "sdd"], "sess-1", self.repo_dir)
        self.assertEqual(code, 1)
        self.assertIn("'root'", err)
        self.assertIn("git_repo", err)

    def test_sdd_config_git_repo_requires_git_ref(self):
        self._write_project_config(sdd_config=dict(_PATTERNS, epics_dir="epics", git_repo=str(self.sdd_root)))
        code, out, err = self.run_cli(["sync", "--source", "sdd"], "sess-1", self.repo_dir)
        self.assertEqual(code, 1)
        self.assertIn("git_repo", err)
        self.assertIn("git_ref", err)

    def test_sdd_config_needs_root_or_git(self):
        self._write_project_config(sdd_config=dict(_PATTERNS, epics_dir="epics"))
        code, out, err = self.run_cli(["sync", "--source", "sdd"], "sess-1", self.repo_dir)
        self.assertEqual(code, 1)
        self.assertIn("'root'", err)


class SyncSddGitTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.project_root = self.root / "projects" / "acme"
        self.repo_dir = self.project_root / "repo"
        self.repo_dir.mkdir(parents=True)
        self._write_project_config()
        self.run_cli(["party", "start", "alpha", "--reason", "test reason"], "sess-1", self.repo_dir)

        self.origin_dir = self.root / "origin.git"
        _git(["init", "--bare", str(self.origin_dir)], self.root)

        self.git_repo_dir = self.root / "sdd-git-repo"
        self.git_repo_dir.mkdir()
        self._init_git_repo(self.git_repo_dir)
        self._write_task_file(
            self.git_repo_dir,
            "widget-rollout",
            "## T01 — Configure retries\n\n**Deps:** —\n\n**Status:** [x] done\n",
        )
        (self.git_repo_dir / "epics" / "widget-rollout" / "discovery.md").write_text("not a task file\n")
        (self.git_repo_dir / "epics" / "nested" / "inner").mkdir(parents=True)
        (self.git_repo_dir / "epics" / "nested" / "inner" / "tasks.md").write_text(
            "## T01 — Too deep\n\n**Deps:** —\n\n**Status:** [ ] pending\n"
        )
        _git(["add", "."], self.git_repo_dir)
        _git(["commit", "-m", "add widget-rollout"], self.git_repo_dir)
        _git(["branch", "-M", "main"], self.git_repo_dir)
        _git(["remote", "add", "origin", str(self.origin_dir)], self.git_repo_dir)
        _git(["push", "-u", "origin", "main"], self.git_repo_dir)

    def _init_git_repo(self, repo_dir):
        _git(["init"], repo_dir)
        _git(["config", "user.email", "guild-tests@example.com"], repo_dir)
        _git(["config", "user.name", "guild-tests"], repo_dir)

    def _write_task_file(self, repo_dir, epic, body):
        epic_dir = repo_dir / "epics" / epic
        epic_dir.mkdir(parents=True, exist_ok=True)
        (epic_dir / "tasks.md").write_text(body)

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

    def _configure_git_sdd(self, git_repo, git_ref):
        self._write_project_config(
            sdd_config=dict(_PATTERNS, git_repo=str(git_repo), git_ref=git_ref, epics_dir="epics")
        )

    def _sync(self):
        return self.run_cli(["sync", "--source", "sdd"], "sess-1", self.repo_dir)

    def test_happy_path_reads_tasks_from_the_fetched_ref(self):
        self._configure_git_sdd(self.git_repo_dir, "origin/main")
        code, out, err = self._sync()
        self.assertEqual(code, 0, err)
        conn = sqlite3.connect(str(self.data_home / "guild" / "guild.db"))
        epic_row = conn.execute("SELECT sdd_path FROM epics WHERE epic = 'widget-rollout'").fetchone()
        task_row = conn.execute("SELECT sdd_status FROM tasks WHERE tid = 'T01'").fetchone()
        epics = [row[0] for row in conn.execute("SELECT epic FROM epics").fetchall()]
        conn.close()
        self.assertEqual(epic_row[0], "git:origin/main:epics/widget-rollout/tasks.md")
        self.assertEqual(task_row[0], "done")
        self.assertEqual(epics, ["widget-rollout"])

    def test_nested_epics_dir_in_the_code_repo_reads_tasks_from_the_fetched_ref(self):
        nested = self.git_repo_dir / "docs" / "specs" / "epics" / "inner-epic"
        nested.mkdir(parents=True)
        (nested / "tasks.md").write_text("## T01 — Nested task\n\n**Deps:** —\n\n**Status:** [x] done\n")
        _git(["add", "."], self.git_repo_dir)
        _git(["commit", "-m", "add nested"], self.git_repo_dir)
        _git(["push", "origin", "main"], self.git_repo_dir)
        self._write_project_config(
            sdd_config=dict(
                _PATTERNS, git_repo=str(self.git_repo_dir), git_ref="origin/main", epics_dir="docs/specs/epics"
            )
        )
        code, out, err = self._sync()
        self.assertEqual(code, 0, err)
        conn = sqlite3.connect(str(self.data_home / "guild" / "guild.db"))
        rows = conn.execute("SELECT epic, sdd_path FROM epics").fetchall()
        conn.close()
        self.assertEqual(rows, [("inner-epic", "git:origin/main:docs/specs/epics/inner-epic/tasks.md")])

    def test_unknown_ref_is_a_clear_error(self):
        self._configure_git_sdd(self.git_repo_dir, "origin/does-not-exist")
        code, out, err = self._sync()
        self.assertEqual(code, 1)
        self.assertIn("git", err)

    def test_zero_tasks_md_under_epics_dir_is_a_clear_error(self):
        self._write_project_config(
            sdd_config=dict(
                _PATTERNS,
                git_repo=str(self.git_repo_dir),
                git_ref="origin/main",
                epics_dir="no-such-dir",
            )
        )
        code, out, err = self._sync()
        self.assertEqual(code, 1)
        self.assertIn("no tasks.md files found", err)

    def test_fetch_failure_is_a_clear_error(self):
        broken_repo_dir = self.root / "sdd-git-repo-broken"
        broken_repo_dir.mkdir()
        self._init_git_repo(broken_repo_dir)
        (broken_repo_dir / "placeholder").write_text("x")
        _git(["add", "."], broken_repo_dir)
        _git(["commit", "-m", "init"], broken_repo_dir)
        _git(["remote", "add", "origin", str(self.root / "no-such-origin")], broken_repo_dir)

        self._configure_git_sdd(broken_repo_dir, "origin/main")
        code, out, err = self._sync()
        self.assertEqual(code, 1)
        self.assertIn("fetch failed", err)

    def test_later_commit_pushed_to_origin_is_picked_up_without_touching_working_copy(self):
        self._configure_git_sdd(self.git_repo_dir, "origin/main")
        code, out, err = self._sync()
        self.assertEqual(code, 0, err)

        status_before = _git(["status", "--porcelain"], self.git_repo_dir)
        head_before = _git(["rev-parse", "HEAD"], self.git_repo_dir)

        editor_dir = self.root / "sdd-git-editor"
        _git(["clone", str(self.origin_dir), str(editor_dir)], self.root)
        self._init_git_repo(editor_dir)
        _git(["checkout", "-B", "main", "origin/main"], editor_dir)
        self._write_task_file(editor_dir, "second-epic", "## T01 — First\n\n**Deps:** —\n\n**Status:** [ ] pending\n")
        _git(["add", "."], editor_dir)
        _git(["commit", "-m", "add second-epic"], editor_dir)
        _git(["push", "origin", "HEAD:main"], editor_dir)

        code, out, err = self._sync()
        self.assertEqual(code, 0, err)

        status_after = _git(["status", "--porcelain"], self.git_repo_dir)
        head_after = _git(["rev-parse", "HEAD"], self.git_repo_dir)
        self.assertEqual(status_before, status_after)
        self.assertEqual(head_before, head_after)

        conn = sqlite3.connect(str(self.data_home / "guild" / "guild.db"))
        row = conn.execute("SELECT sdd_path FROM epics WHERE epic = 'second-epic'").fetchone()
        conn.close()
        self.assertEqual(row[0], "git:origin/main:epics/second-epic/tasks.md")


if __name__ == "__main__":
    import unittest

    unittest.main()
