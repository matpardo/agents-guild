import json
import sqlite3
import subprocess
from datetime import timedelta
from unittest import mock

from guild import db, locking, origin, paths, timeutil
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

    def _two_generations(self):
        self.run_cli(["handoff", "--in-flight", "x", "--learned", "y"], "sess-1", self.repo_dir)
        self.run_cli(["party", "resume", "alpha"], "sess-2", self.repo_dir)
        self.run_cli(["handoff", "--in-flight", "x", "--learned", "y"], "sess-2", self.repo_dir)
        return paths.handoffs_dir() / "alpha-g1.md"

    def test_sync_gh_prunes_superseded_handoffs(self):
        first = self._two_generations()
        code, out, err = self.run_cli(["sync", "--source", "gh"], "sess-2", self.repo_dir)
        self.assertEqual(code, 0, err)
        self.assertEqual(out, "")
        self.assertFalse(first.exists())

    def test_sync_gh_skips_prune_silently_when_locked(self):
        first = self._two_generations()
        with locking.try_lock(paths.state_dir() / "handoff-prune", "prune.lock"):
            code, out, err = self.run_cli(["sync", "--source", "gh"], "sess-2", self.repo_dir)
        self.assertEqual((code, err), (0, ""))
        self.assertTrue(first.exists())

    def test_sync_gh_reports_prune_failure_without_aborting(self):
        first = self._two_generations()
        with mock.patch("guild.handoff_prune.plan", side_effect=GuildError("boom", 1)):
            code, out, err = self.run_cli(["sync", "--source", "gh"], "sess-2", self.repo_dir)
        self.assertEqual(code, 1)
        self.assertIn("handoff prune failed: boom", err)
        self.assertTrue(first.exists())

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

    def _sync_rollup(self, rollup):
        self.write_gh_fixture(
            "view_acme-app_1",
            {
                "state": "OPEN", "isDraft": False, "headRefName": "feature/x", "title": "t",
                "statusCheckRollup": rollup,
            },
        )
        code, out, err = self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0)
        conn = db.connect(paths.db_path())
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT checks_failing, checks_passing, checks_pending FROM prs WHERE number = 1"
        ).fetchone()
        conn.close()
        return (row["checks_failing"], row["checks_passing"], row["checks_pending"])

    def test_status_context_failure_counts_as_failing(self):
        rollup = [
            {"__typename": "StatusContext", "state": "FAILURE"},
            {"__typename": "StatusContext", "state": "ERROR"},
            {"__typename": "StatusContext", "state": "SUCCESS"},
        ]
        self.assertEqual(self._sync_rollup(rollup), (2, 1, 0))

    def test_pending_checks_are_counted(self):
        rollup = [
            {"__typename": "CheckRun", "status": "QUEUED", "conclusion": ""},
            {"__typename": "CheckRun", "status": "IN_PROGRESS", "conclusion": ""},
            {"__typename": "CheckRun", "status": "COMPLETED", "conclusion": "SUCCESS"},
            {"__typename": "CheckRun", "status": "COMPLETED", "conclusion": "SKIPPED"},
            {"__typename": "StatusContext", "state": "PENDING"},
            {"__typename": "StatusContext", "state": "EXPECTED"},
        ]
        self.assertEqual(self._sync_rollup(rollup), (0, 1, 4))

    def _synced_payloads(self):
        conn = db.connect(paths.db_path())
        rows = conn.execute("SELECT payload FROM events WHERE kind = 'pr.synced' ORDER BY seq").fetchall()
        conn.close()
        return [json.loads(row["payload"]) for row in rows]

    def test_synced_event_records_the_head_commit(self):
        self.write_gh_fixture(
            "view_acme-app_1",
            {
                "state": "OPEN", "isDraft": True, "headRefName": "feature/x", "title": "t",
                "headRefOid": "abc123def456",
            },
        )
        code, out, err = self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        self.assertEqual(self._synced_payloads()[-1]["head_sha"], "abc123def456")

    def test_synced_event_without_head_commit_records_none(self):
        code, out, err = self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        self.assertIsNone(self._synced_payloads()[-1]["head_sha"])

    def test_synced_event_records_whether_the_pr_comes_from_a_fork(self):
        self.write_gh_fixture(
            "view_acme-app_1",
            {
                "state": "OPEN", "isDraft": True, "headRefName": "feature/x", "title": "t",
                "isCrossRepository": True,
            },
        )
        self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)
        self.assertIs(self._synced_payloads()[-1]["cross_repository"], True)

    def test_synced_event_without_fork_info_records_none(self):
        self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)
        self.assertIsNone(self._synced_payloads()[-1]["cross_repository"])

    def test_pr_view_asks_gh_whether_the_pr_is_cross_repository(self):
        with mock.patch("guild.adapters.github.pr_view", return_value={"state": "OPEN", "isDraft": True}) as view:
            self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)
        self.assertIn("isCrossRepository", view.call_args[0][3])

    def test_pr_view_asks_gh_for_the_head_commit(self):
        with mock.patch("guild.adapters.github.pr_view", return_value={"state": "OPEN", "isDraft": True}) as view:
            self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)
        self.assertIn("headRefOid", view.call_args[0][3])

    def test_board_shows_pending_checks_glyph(self):
        self._sync_rollup([{"__typename": "StatusContext", "state": "PENDING"}])
        code, out, err = self.run_cli(["board"], "sess-1", self.repo_dir)
        self.assertIn("app#1  ready  ✗0 ✓0 ⏳1", out)

    def test_board_says_no_checks_only_when_every_count_is_zero(self):
        self._sync_rollup([])
        code, out, err = self.run_cli(["board"], "sess-1", self.repo_dir)
        self.assertIn("app#1  ready  no checks", out)

    def test_old_pr_synced_event_without_checks_pending_replays(self):
        self._sync_rollup([{"conclusion": "FAILURE"}])
        conn = db.connect(paths.db_path())
        conn.execute("UPDATE events SET payload = json_remove(payload, '$.checks_pending') WHERE kind = 'pr.synced'")
        conn.commit()
        conn.close()
        code, out, err = self.run_cli(["rebuild"], None, None)
        self.assertEqual(code, 0)
        conn = db.connect(paths.db_path())
        row = conn.execute("SELECT checks_failing, checks_pending FROM prs WHERE number = 1").fetchone()
        conn.close()
        self.assertEqual((row[0], row[1]), (1, None))

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
            sync_commands.run(ctx, "bogus", None)
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

    def _track_loose(self, session_id, number, extra):
        self.write_gh_fixture(
            "view_acme-app_{}".format(number),
            {"state": "OPEN", "isDraft": True, "headRefName": "feature/y", "title": "t"},
        )
        code, out, err = self.run_cli(
            ["pr", "track", "acme/app#{}".format(number), "--what", "fix the pipe", "--waits", "y"] + extra,
            session_id, self.repo_dir,
        )
        self.assertEqual(code, 0, err)
        self.write_gh_fixture(
            "view_acme-app_{}".format(number),
            {
                "state": "MERGED", "isDraft": False, "headRefName": "feature/y", "title": "t",
                "mergedAt": "2026-01-01T00:00:00Z", "statusCheckRollup": [],
            },
        )

    def test_merge_notice_of_a_card_pr_shows_the_card(self):
        self.run_cli(["raid", "join", "release", "--ttl", "1h"], "sess-1", self.repo_dir)
        self.run_cli(["raid", "join", "release", "--ttl", "1h"], "sess-2", self.repo_dir)
        self._track_loose("sess-1", 2, ["--card", "ABC-123"])
        self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["inbox", "--since-last"], "sess-2", self.repo_dir)
        self.assertIn("acme/app#2 merged in main (ABC-123: fix the pipe)", out)
        self.assertNotIn("None", out)

    def test_merge_notice_of_a_seeded_pr_never_shows_none(self):
        self.run_cli(["raid", "join", "release", "--ttl", "1h"], "sess-1", self.repo_dir)
        self.run_cli(["raid", "join", "release", "--ttl", "1h"], "sess-2", self.repo_dir)
        seed_file = self.root / "seed.json"
        seed_file.write_text(
            json.dumps(
                {"prs": [{"repo": "acme/app", "number": 3, "party": "alpha", "what": "seeded work"}]}
            )
        )
        self.run_cli(["seed", str(seed_file)], None, None)
        self.write_gh_fixture(
            "view_acme-app_3",
            {
                "state": "MERGED", "isDraft": False, "headRefName": "feature/z", "title": "t",
                "mergedAt": "2026-01-01T00:00:00Z", "statusCheckRollup": [],
            },
        )
        self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["inbox", "--since-last"], "sess-2", self.repo_dir)
        self.assertIn("acme/app#3 merged in main (seeded work)", out)
        self.assertNotIn("None", out)

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
