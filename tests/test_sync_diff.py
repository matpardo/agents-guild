import json
import sqlite3
from unittest import mock

from guild.adapters import github
from tests.testutil import GuildTestCase

_OPEN_VIEW = {
    "state": "OPEN",
    "isDraft": False,
    "headRefName": "feature/x",
    "title": "t",
    "statusCheckRollup": [{"conclusion": "SUCCESS"}],
    "mergeable": "MERGEABLE",
}


def _diff_fixture(paths, additions, deletions, created_at):
    return {
        "files": [{"path": path} for path in paths],
        "additions": additions,
        "deletions": deletions,
        "createdAt": created_at,
    }


class SyncDiffTestCase(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self._set_shared_areas(["shared/**", "config/locales/es.yml"])
        self.run_cli(
            ["party", "start", "alpha", "--reason", "test reason", "--goal", "test goal", "--done-when", "test done"],
            "sess-1",
            self.repo_dir,
        )
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", self.repo_dir)
        self.run_cli(
            ["task", "add", "demo/T01", "--title", "First", "--reason", "serves the goal"], "sess-1", self.repo_dir
        )
        self.write_gh_fixture(
            "view_acme-app_1",
            {"state": "OPEN", "isDraft": True, "headRefName": "feature/x", "title": "t"},
        )
        self.run_cli(
            ["pr", "track", "acme/app#1", "--task", "demo/T01", "--what", "x", "--waits", "y"],
            "sess-1",
            self.repo_dir,
        )
        self.write_gh_fixture("view_acme-app_1", _OPEN_VIEW)
        self.write_gh_fixture(
            "view_files_acme-app_1",
            _diff_fixture(["shared/a.yml", "config/locales/es.yml", "src/app.py"], 10, 2, "2026-09-01T10:00:00Z"),
        )

    def _set_shared_areas(self, globs):
        config_file = self.config_home / "guild" / "projects" / "acme.json"
        data = json.loads(config_file.read_text())
        data["shared_areas"] = globs
        data["shared_area_claim_ttl"] = "2h"
        config_file.write_text(json.dumps(data))

    def _sync(self):
        return self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)

    def _query(self, sql):
        conn = sqlite3.connect(str(self.data_home / "guild" / "guild.db"))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql).fetchall()
        conn.close()
        return rows

    def _globs(self):
        rows = self._query("SELECT glob FROM pr_shared_areas WHERE repo = 'acme/app' AND number = 1")
        return sorted(row["glob"] for row in rows)

    def _pr_row(self):
        return self._query("SELECT additions, deletions, created_at FROM prs WHERE number = 1")[0]


class RaidMemberFetchTests(SyncDiffTestCase):
    def setUp(self):
        super().setUp()
        self.run_cli(["raid", "join", "ci", "--ttl", "1h"], "sess-1", self.repo_dir)

    def test_stores_matched_globs_and_diff_size(self):
        code, out, err = self._sync()
        self.assertEqual(code, 0, err)
        self.assertEqual(self._globs(), ["config/locales/es.yml", "shared/**"])
        row = self._pr_row()
        self.assertEqual((row["additions"], row["deletions"]), (10, 2))
        self.assertEqual(row["created_at"], "2026-09-01T10:00:00Z")

    def test_one_call_per_pr_per_sync(self):
        with mock.patch.object(github, "pr_diff", wraps=github.pr_diff) as pr_diff:
            self._sync()
        self.assertEqual(pr_diff.call_count, 1)

    def test_resync_replaces_globs(self):
        self._sync()
        self.write_gh_fixture("view_files_acme-app_1", _diff_fixture(["shared/b.yml"], 3, 1, "2026-09-01T10:00:00Z"))
        self._sync()
        self.assertEqual(self._globs(), ["shared/**"])
        self.assertEqual(self._pr_row()["additions"], 3)

    def test_fetch_failure_fails_sync_and_keeps_previous_rows(self):
        self._sync()
        self.write_gh_error("view_files_acme-app_1", "boom")
        code, out, err = self._sync()
        self.assertEqual(code, 1)
        self.assertIn("acme/app#1", err)
        self.assertIn("boom", err)
        self.assertEqual(self._globs(), ["config/locales/es.yml", "shared/**"])
        self.assertEqual(self._pr_row()["additions"], 10)

    def test_fetch_failure_still_syncs_the_pr(self):
        self.write_gh_error("view_files_acme-app_1", "boom")
        code, out, err = self._sync()
        self.assertEqual(code, 1)
        rows = self._query("SELECT lifecycle, checks_passing FROM prs WHERE number = 1")
        self.assertEqual(rows[0]["checks_passing"], 1)

    def test_rebuild_reproduces_rows(self):
        self._sync()
        self.run_cli(["rebuild"], None, None)
        self.assertEqual(self._globs(), ["config/locales/es.yml", "shared/**"])
        row = self._pr_row()
        self.assertEqual((row["additions"], row["deletions"], row["created_at"]), (10, 2, "2026-09-01T10:00:00Z"))

    def test_merged_pr_is_fetched_once_for_merge_handling_only(self):
        self.write_gh_fixture(
            "view_acme-app_1",
            {
                "state": "MERGED",
                "isDraft": False,
                "headRefName": "feature/x",
                "title": "t",
                "mergedAt": "2026-01-01T00:00:00Z",
                "statusCheckRollup": [],
            },
        )
        with mock.patch.object(github, "pr_diff", wraps=github.pr_diff) as pr_diff:
            code, out, err = self._sync()
        self.assertEqual(code, 0, err)
        self.assertEqual(pr_diff.call_count, 1)
        self.assertEqual(self._globs(), [])

    def test_project_without_shared_areas_makes_no_call(self):
        config_file = self.config_home / "guild" / "projects" / "acme.json"
        data = json.loads(config_file.read_text())
        del data["shared_areas"]
        del data["shared_area_claim_ttl"]
        config_file.write_text(json.dumps(data))
        with mock.patch.object(github, "pr_diff", wraps=github.pr_diff) as pr_diff:
            code, out, err = self._sync()
        self.assertEqual(code, 0, err)
        self.assertEqual(pr_diff.call_count, 0)


class ClaimHolderFetchTests(SyncDiffTestCase):
    def test_area_claim_holder_outside_a_raid_is_fetched(self):
        self.run_cli(["claim", "area:shared/**", "--ttl", "2h"], "sess-1", self.repo_dir)
        code, out, err = self._sync()
        self.assertEqual(code, 0, err)
        self.assertEqual(self._globs(), ["config/locales/es.yml", "shared/**"])

    def test_task_claim_alone_makes_no_call(self):
        self.run_cli(["claim", "task:demo/T01", "--ttl", "2h"], "sess-1", self.repo_dir)
        with mock.patch.object(github, "pr_diff", wraps=github.pr_diff) as pr_diff:
            code, out, err = self._sync()
        self.assertEqual(code, 0, err)
        self.assertEqual(pr_diff.call_count, 0)


class OutsideRaidTests(SyncDiffTestCase):
    def test_party_without_raid_or_claims_makes_no_call(self):
        with mock.patch.object(github, "pr_diff", wraps=github.pr_diff) as pr_diff:
            code, out, err = self._sync()
        self.assertEqual(code, 0, err)
        self.assertEqual(pr_diff.call_count, 0)
        self.assertEqual(self._globs(), [])
        self.assertIsNone(self._pr_row()["additions"])
