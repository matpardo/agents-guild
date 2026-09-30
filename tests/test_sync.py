import json
import sqlite3
import subprocess
from datetime import timedelta
from unittest import mock

from guild import db, origin, paths, timeutil
from guild.commands import sync as sync_commands
from guild.context import RunContext
from guild.errors import GuildError
from tests.testutil import GuildTestCase


class SyncTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha"], "sess-1", self.repo_dir)
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", self.repo_dir)
        self.run_cli(["task", "add", "demo/T01", "--title", "First"], "sess-1", self.repo_dir)
        self.write_gh_fixture(
            "view_acme-app_1",
            {"state": "OPEN", "isDraft": True, "headRefName": "feature/x", "title": "t"},
        )
        self.run_cli(
            ["pr", "track", "acme/app#1", "--task", "demo/T01", "--what", "x", "--waits", "y"],
            "sess-1", self.repo_dir,
        )

    def test_sync_flips_merged_pr(self):
        self.write_gh_fixture(
            "view_acme-app_1",
            {
                "state": "MERGED", "isDraft": False, "headRefName": "feature/x", "title": "t",
                "mergedAt": "2026-01-01T00:00:00Z",
                "statusCheckRollup": [{"conclusion": "SUCCESS"}, {"conclusion": "FAILURE"}],
            },
        )
        code, out, err = self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0)
        code, out, err = self.run_cli(["board"], "sess-1", self.repo_dir)
        self.assertIn("app#1  merged  ✗1 ✓1", out)

    def test_sync_closes_notice_when_until_met(self):
        self.run_cli(
            [
                "notice", "create", "waiting on merge", "--to", "guild", "--ttl", "8h",
                "--until", "pr:acme/app#1:merged",
            ],
            None, None,
        )
        self.write_gh_fixture(
            "view_acme-app_1",
            {
                "state": "MERGED", "isDraft": False, "headRefName": "feature/x", "title": "t",
                "mergedAt": "2026-01-01T00:00:00Z", "statusCheckRollup": [],
            },
        )
        self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["notices"], None, None)
        self.assertEqual(out, "")

    def test_sync_reports_gh_failure_and_continues(self):
        self.write_gh_error("view_acme-app_1", "rate limited")
        code, out, err = self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)
        self.assertEqual(code, 1)
        self.assertIn("sync failed for acme/app#1", err)

    def test_unimplemented_source_rejected(self):
        conn = db.connect(paths.db_path())
        ctx = RunContext(
            conn, "sess-1", self.repo_dir, timeutil.utcnow(), origin.current_origin(), None, None, None
        )
        with self.assertRaises(GuildError) as raised:
            sync_commands.run(ctx, "bogus")
        conn.close()
        self.assertIn("not implemented", raised.exception.message)


class GhMergeNoticeTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha"], "sess-1", self.repo_dir)
        self.run_cli(["party", "start", "beta"], "sess-2", self.repo_dir)
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", self.repo_dir)
        self.run_cli(["task", "add", "demo/T01", "--title", "First"], "sess-1", self.repo_dir)
        self.write_gh_fixture(
            "view_acme-app_1",
            {"state": "OPEN", "isDraft": True, "headRefName": "feature/x", "title": "t"},
        )
        self.run_cli(
            ["pr", "track", "acme/app#1", "--task", "demo/T01", "--what", "ship the thing", "--waits", "y"],
            "sess-1", self.repo_dir,
        )

    def _merge_fixture(self):
        self.write_gh_fixture(
            "view_acme-app_1",
            {
                "state": "MERGED", "isDraft": False, "headRefName": "feature/x", "title": "t",
                "mergedAt": "2026-01-01T00:00:00Z", "statusCheckRollup": [],
            },
        )

    def _set_shared_areas(self, globs):
        config_file = self.config_home / "guild" / "projects" / "acme.json"
        data = json.loads(config_file.read_text())
        data["shared_areas"] = globs
        data["shared_area_claim_ttl"] = "2h"
        config_file.write_text(json.dumps(data))

    def _notices_rows(self, announces):
        conn = sqlite3.connect(str(self.data_home / "guild" / "guild.db"))
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM notices WHERE announces = ?", (announces,)).fetchall()
        conn.close()
        return rows

    def test_merge_posts_one_notice_per_owner_raid(self):
        self.run_cli(["raid", "join", "release", "--ttl", "1h"], "sess-1", self.repo_dir)
        self.run_cli(["raid", "join", "ci", "--ttl", "1h"], "sess-1", self.repo_dir)
        self._merge_fixture()
        code, out, err = self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        code, out, err = self.run_cli(["notices"], None, None)
        matches = [line for line in out.splitlines() if "acme/app#1 merged in main" in line]
        self.assertEqual(len(matches), 2)

    def test_notice_delivered_to_other_member_not_owner(self):
        self.run_cli(["raid", "join", "release", "--ttl", "1h"], "sess-1", self.repo_dir)
        self.run_cli(["raid", "join", "release", "--ttl", "1h"], "sess-2", self.repo_dir)
        self._merge_fixture()
        code, out, err = self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        code, out, err = self.run_cli(["inbox", "--since-last"], "sess-2", self.repo_dir)
        self.assertIn("acme/app#1 merged in main (demo/T01: ship the thing)", out)
        code, out, err = self.run_cli(["inbox", "--since-last"], "sess-1", self.repo_dir)
        self.assertNotIn("acme/app#1 merged", out)

    def test_no_notice_when_owner_in_no_raid(self):
        self._merge_fixture()
        code, out, err = self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        code, out, err = self.run_cli(["notices"], None, None)
        self.assertEqual(out, "")

    def test_no_duplicate_notice_on_resync(self):
        self.run_cli(["raid", "join", "release", "--ttl", "1h"], "sess-1", self.repo_dir)
        self._merge_fixture()
        self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)
        self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)
        self.assertEqual(len(self._notices_rows("pr:acme/app#1")), 1)

    def test_no_duplicate_notice_after_rebuild_then_sync(self):
        self.run_cli(["raid", "join", "release", "--ttl", "1h"], "sess-1", self.repo_dir)
        self._merge_fixture()
        self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)
        self.run_cli(["rebuild"], None, None)
        self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)
        self.assertEqual(len(self._notices_rows("pr:acme/app#1")), 1)

    def test_shared_areas_line_present_when_touched(self):
        self._set_shared_areas(["shared/**"])
        self.write_gh_fixture("view_files_acme-app_1", {"files": [{"path": "shared/config.yml"}], "additions": 1, "deletions": 0, "createdAt": "2026-01-01T00:00:00Z"})
        self.run_cli(["raid", "join", "release", "--ttl", "1h"], "sess-1", self.repo_dir)
        self._merge_fixture()
        self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["notices"], None, None)
        self.assertIn("Shared areas touched: shared/**", out)

    def test_shared_areas_line_absent_when_not_configured(self):
        self.run_cli(["raid", "join", "release", "--ttl", "1h"], "sess-1", self.repo_dir)
        self._merge_fixture()
        self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["notices"], None, None)
        self.assertNotIn("Shared areas touched", out)

    def test_shared_areas_line_absent_when_no_files_match(self):
        self._set_shared_areas(["shared/**"])
        self.write_gh_fixture("view_files_acme-app_1", {"files": [{"path": "src/app.py"}], "additions": 1, "deletions": 0, "createdAt": "2026-01-01T00:00:00Z"})
        self.run_cli(["raid", "join", "release", "--ttl", "1h"], "sess-1", self.repo_dir)
        self._merge_fixture()
        self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["notices"], None, None)
        self.assertNotIn("Shared areas touched", out)

    def test_files_fetch_failure_still_posts_notice_and_fails_sync(self):
        self._set_shared_areas(["shared/**"])
        self.write_gh_error("view_files_acme-app_1", "boom")
        self.run_cli(["raid", "join", "release", "--ttl", "1h"], "sess-1", self.repo_dir)
        self._merge_fixture()
        code, out, err = self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)
        self.assertEqual(code, 1)
        self.assertIn("acme/app#1", err)
        code, out, err = self.run_cli(["notices"], None, None)
        self.assertIn("acme/app#1 merged in main", out)
        self.assertNotIn("Shared areas touched", out)

    def test_already_merged_at_track_time_does_not_announce(self):
        self.write_gh_fixture(
            "view_acme-app_2",
            {"state": "MERGED", "isDraft": False, "headRefName": "feature/y", "title": "t2"},
        )
        self.run_cli(
            ["pr", "track", "acme/app#2", "--task", "demo/T01", "--what", "already merged", "--waits", "y"],
            "sess-1", self.repo_dir,
        )
        self.run_cli(["raid", "join", "release", "--ttl", "1h"], "sess-1", self.repo_dir)
        self.write_gh_fixture(
            "view_acme-app_2",
            {
                "state": "MERGED", "isDraft": False, "headRefName": "feature/y", "title": "t2",
                "mergedAt": "2026-01-01T00:00:00Z", "statusCheckRollup": [],
            },
        )
        code, out, err = self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        code, out, err = self.run_cli(["notices"], None, None)
        self.assertEqual(out, "")

    def test_expired_raid_membership_not_announced(self):
        self.run_cli(["raid", "join", "release", "--ttl", "30m"], "sess-1", self.repo_dir)
        self._merge_fixture()
        future = timeutil.utcnow() + timedelta(hours=1)
        with mock.patch("guild.timeutil.utcnow", return_value=future):
            code, out, err = self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        code, out, err = self.run_cli(["notices"], None, None)
        self.assertEqual(out, "")


class GhMergeReleasesClaimsTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        config_file = self.config_home / "guild" / "projects" / "acme.json"
        data = json.loads(config_file.read_text())
        data["shared_areas"] = ["shared/**", "db/migrate/*"]
        data["shared_area_claim_ttl"] = "2h"
        config_file.write_text(json.dumps(data))
        self.run_cli(["party", "start", "alpha"], "sess-1", self.repo_dir)
        self.run_cli(["party", "start", "beta"], "sess-2", self.repo_dir)
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", self.repo_dir)
        self.run_cli(["task", "add", "demo/T01", "--title", "First"], "sess-1", self.repo_dir)
        self.write_gh_fixture(
            "view_acme-app_1",
            {"state": "OPEN", "isDraft": True, "headRefName": "feature/x", "title": "t"},
        )
        self.run_cli(
            ["pr", "track", "acme/app#1", "--task", "demo/T01", "--what", "ship", "--waits", "y"],
            "sess-1", self.repo_dir,
        )
        self.write_gh_fixture("view_files_acme-app_1", {"files": [{"path": "shared/config.yml"}], "additions": 1, "deletions": 0, "createdAt": "2026-01-01T00:00:00Z"})

    def _merge_fixture(self):
        self.write_gh_fixture(
            "view_acme-app_1",
            {
                "state": "MERGED", "isDraft": False, "headRefName": "feature/x", "title": "t",
                "mergedAt": "2026-01-01T00:00:00Z", "statusCheckRollup": [],
            },
        )

    def _claims(self):
        conn = sqlite3.connect(str(self.data_home / "guild" / "guild.db"))
        rows = conn.execute("SELECT area, party FROM claims ORDER BY area").fetchall()
        conn.close()
        return rows

    def _sync(self):
        return self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)

    def _files_calls_fixture_removed(self):
        (self.gh_fixtures_dir / "view_files_acme-app_1.json").unlink()

    def test_releases_owner_claims_matching_touched_files(self):
        self.run_cli(["claim", "area:shared/**", "--ttl", "2h"], "sess-1", self.repo_dir)
        self._merge_fixture()
        code, out, err = self._sync()
        self.assertEqual(code, 0, err)
        self.assertEqual(self._claims(), [])

    def test_non_matching_owner_claim_stays(self):
        self.run_cli(["claim", "area:shared/**", "--ttl", "2h"], "sess-1", self.repo_dir)
        self.run_cli(["claim", "area:db/migrate/*", "--ttl", "2h"], "sess-1", self.repo_dir)
        self._merge_fixture()
        self._sync()
        self.assertEqual(self._claims(), [("area:db/migrate/*", "alpha")])

    def test_claim_held_by_other_party_stays(self):
        self.run_cli(["claim", "area:shared/**", "--ttl", "2h"], "sess-2", self.repo_dir)
        self.run_cli(["claim", "area:db/migrate/*", "--ttl", "2h"], "sess-1", self.repo_dir)
        self._merge_fixture()
        code, out, err = self._sync()
        self.assertEqual(code, 0, err)
        self.assertEqual(self._claims(), [("area:db/migrate/*", "alpha"), ("area:shared/**", "beta")])

    def test_task_claims_stay(self):
        self.run_cli(["claim", "area:shared/**", "--ttl", "2h"], "sess-1", self.repo_dir)
        self.run_cli(["claim", "task:demo/T01", "--ttl", "2h"], "sess-1", self.repo_dir)
        self._merge_fixture()
        self._sync()
        self.assertEqual(self._claims(), [("task:demo/T01", "alpha")])

    def test_project_without_shared_areas_makes_no_files_call(self):
        config_file = self.config_home / "guild" / "projects" / "acme.json"
        data = json.loads(config_file.read_text())
        del data["shared_areas"]
        config_file.write_text(json.dumps(data))
        self.run_cli(["raid", "join", "release", "--ttl", "1h"], "sess-1", self.repo_dir)
        self._files_calls_fixture_removed()
        self._merge_fixture()
        code, out, err = self._sync()
        self.assertEqual(code, 0, err)

    def test_owner_without_area_claims_or_raid_makes_no_files_call(self):
        self.run_cli(["claim", "task:demo/T01", "--ttl", "2h"], "sess-1", self.repo_dir)
        self._files_calls_fixture_removed()
        self._merge_fixture()
        code, out, err = self._sync()
        self.assertEqual(code, 0, err)

    def test_files_fetched_once_when_raid_and_claim(self):
        self.run_cli(["claim", "area:shared/**", "--ttl", "2h"], "sess-1", self.repo_dir)
        self.run_cli(["raid", "join", "release", "--ttl", "1h"], "sess-1", self.repo_dir)
        self._merge_fixture()
        with mock.patch(
            "guild.adapters.github.pr_diff",
            return_value={
                "paths": ["shared/config.yml"], "additions": 1, "deletions": 0,
                "created_at": "2026-01-01T00:00:00Z",
            },
        ) as pr_diff:
            code, out, err = self._sync()
        self.assertEqual(code, 0, err)
        self.assertEqual(pr_diff.call_count, 1)

    def test_files_fetch_failure_releases_nothing_and_fails_sync(self):
        self.run_cli(["claim", "area:shared/**", "--ttl", "2h"], "sess-1", self.repo_dir)
        self.write_gh_error("view_files_acme-app_1", "boom")
        self._merge_fixture()
        code, out, err = self._sync()
        self.assertEqual(code, 1)
        self.assertIn("acme/app#1", err)
        self.assertEqual(self._claims(), [("area:shared/**", "alpha")])

    def test_merge_notice_lists_released_globs(self):
        self.run_cli(["claim", "area:shared/**", "--ttl", "2h"], "sess-1", self.repo_dir)
        self.run_cli(["raid", "join", "release", "--ttl", "1h"], "sess-1", self.repo_dir)
        self._merge_fixture()
        self._sync()
        code, out, err = self.run_cli(["notices"], None, None)
        self.assertIn("Shared areas touched: shared/** Released: shared/**.", out)

    def test_notice_has_no_released_text_when_nothing_released(self):
        self.run_cli(["raid", "join", "release", "--ttl", "1h"], "sess-1", self.repo_dir)
        self._merge_fixture()
        self._sync()
        code, out, err = self.run_cli(["notices"], None, None)
        self.assertNotIn("Released:", out)

    def test_other_party_can_commit_after_release(self):
        repo = self.repo_dir
        for command in (
            ["git", "init", "-q"],
            ["git", "config", "user.email", "t@t.com"],
            ["git", "config", "user.name", "t"],
            ["git", "commit", "--allow-empty", "-q", "-m", "init"],
        ):
            subprocess.run(command, cwd=str(repo), check=True)
        target = repo / "shared" / "config.yml"
        target.parent.mkdir()
        target.write_text("change")
        subprocess.run(["git", "add", "shared/config.yml"], cwd=str(repo), check=True)
        self.run_cli(["claim", "area:shared/**", "--ttl", "2h"], "sess-1", repo)
        code, out, err = self.run_cli(["hook", "pre-commit"], "sess-2", repo)
        self.assertEqual(code, 1)
        self._merge_fixture()
        self._sync()
        code, out, err = self.run_cli(["hook", "pre-commit"], "sess-2", repo)
        self.assertEqual(code, 0, err)

    def test_resync_is_noop(self):
        self.run_cli(["claim", "area:shared/**", "--ttl", "2h"], "sess-1", self.repo_dir)
        self._merge_fixture()
        self._sync()
        self.run_cli(["claim", "area:shared/**", "--ttl", "2h"], "sess-2", self.repo_dir)
        code, out, err = self._sync()
        self.assertEqual(code, 0, err)
        self.assertEqual(self._claims(), [("area:shared/**", "beta")])

    def test_rebuild_reproduces_state(self):
        self.run_cli(["claim", "area:shared/**", "--ttl", "2h"], "sess-1", self.repo_dir)
        self.run_cli(["claim", "area:db/migrate/*", "--ttl", "2h"], "sess-1", self.repo_dir)
        self._merge_fixture()
        self._sync()
        before = self._claims()
        self.run_cli(["rebuild"], None, None)
        self.assertEqual(self._claims(), before)
        self.assertEqual(before, [("area:db/migrate/*", "alpha")])


if __name__ == "__main__":
    import unittest

    unittest.main()
