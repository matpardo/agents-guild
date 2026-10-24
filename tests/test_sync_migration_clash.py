import json
import sqlite3
from unittest import mock

from guild.adapters import github
from tests.testutil import GuildTestCase

_OPEN_VIEW = {
    "state": "OPEN", "isDraft": False, "headRefName": "feature/x", "title": "t",
    "statusCheckRollup": [{"conclusion": "SUCCESS"}], "mergeable": "MERGEABLE",
}


def _files_fixture(paths):
    return {
        "files": [{"path": path} for path in paths],
        "additions": 1,
        "deletions": 0,
        "createdAt": "2026-09-01T10:00:00Z",
    }


class MigrationClashTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self._set_migration_paths(["db/migrate/*"])
        self.run_cli(["party", "start", "alpha", "--reason", "test reason"], "sess-1", self.repo_dir)
        self.run_cli(["party", "start", "beta", "--reason", "test reason"], "sess-2", self.repo_dir)
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", self.repo_dir)
        self.run_cli(["task", "add", "demo/T01", "--title", "First"], "sess-1", self.repo_dir)
        self.run_cli(["task", "add", "demo/T02", "--title", "Second"], "sess-1", self.repo_dir)
        self._track(1, "demo/T01", "sess-1")
        self._track(2, "demo/T02", "sess-2")
        self.run_cli(["raid", "join", "db", "--ttl", "1h"], "sess-1", self.repo_dir)
        self.run_cli(["raid", "join", "web", "--ttl", "1h"], "sess-2", self.repo_dir)
        self._set_files(1, ["db/migrate/20260901_add_users.rb"])
        self._set_files(2, ["db/migrate/20260901_add_orders.rb"])

    def _track(self, number, task, session):
        name = "view_acme-app_{}".format(number)
        self.write_gh_fixture(name, {"state": "OPEN", "isDraft": True, "headRefName": "f", "title": "t"})
        self.run_cli(
            ["pr", "track", "acme/app#{}".format(number), "--task", task, "--what", "x", "--waits", "y"],
            session, self.repo_dir,
        )
        self.write_gh_fixture(name, _OPEN_VIEW)

    def _set_files(self, number, paths):
        self.write_gh_fixture("view_files_acme-app_{}".format(number), _files_fixture(paths))

    def _config_file(self):
        return self.config_home / "guild" / "projects" / "acme.json"

    def _set_migration_paths(self, globs):
        data = json.loads(self._config_file().read_text())
        data["migration_paths"] = globs
        self._config_file().write_text(json.dumps(data))

    def _clear_migration_paths(self):
        data = json.loads(self._config_file().read_text())
        del data["migration_paths"]
        self._config_file().write_text(json.dumps(data))

    def _sync(self):
        return self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)

    def _clash_notices(self):
        conn = sqlite3.connect(str(self.data_home / "guild" / "guild.db"))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM notices WHERE announces LIKE 'migration:%' ORDER BY id"
        ).fetchall()
        conn.close()
        return rows

    def test_shared_version_posts_notice_to_each_party_raid(self):
        code, out, err = self._sync()
        self.assertEqual(code, 0, err)
        rows = self._clash_notices()
        self.assertEqual(sorted(row["scope"] for row in rows), ["raid:db", "raid:web"])
        for row in rows:
            self.assertIn("20260901", row["text"])
            self.assertIn("acme/app#1", row["text"])
            self.assertIn("acme/app#2", row["text"])

    def test_resync_does_not_repost(self):
        self._sync()
        self._sync()
        self.assertEqual(len(self._clash_notices()), 2)

    def test_distinct_versions_post_nothing(self):
        self._set_files(2, ["db/migrate/20260902_add_orders.rb"])
        self._sync()
        self.assertEqual(self._clash_notices(), [])

    def test_non_migration_files_ignored(self):
        self._set_files(1, ["src/20260901_x.rb"])
        self._set_files(2, ["src/20260901_y.rb"])
        self._sync()
        self.assertEqual(self._clash_notices(), [])

    def test_files_without_leading_digits_ignored(self):
        self._set_files(1, ["db/migrate/add_users.rb"])
        self._set_files(2, ["db/migrate/add_users.rb"])
        self._sync()
        self.assertEqual(self._clash_notices(), [])

    def test_same_pr_with_duplicate_version_is_not_a_clash(self):
        self._set_files(1, ["db/migrate/20260901_a.rb", "db/migrate/20260901_b.rb"])
        self._set_files(2, ["db/migrate/20260902_c.rb"])
        self._sync()
        self.assertEqual(self._clash_notices(), [])

    def test_unset_migration_paths_skips_check_and_diff_calls(self):
        self._clear_migration_paths()
        with mock.patch.object(github, "pr_diff", wraps=github.pr_diff) as pr_diff:
            self._sync()
        self.assertEqual(pr_diff.call_count, 0)
        self.assertEqual(self._clash_notices(), [])

    def test_party_outside_raid_gets_no_notice(self):
        self.run_cli(["raid", "leave", "web"], "sess-2", self.repo_dir)
        self._sync()
        self.assertEqual([row["scope"] for row in self._clash_notices()], ["raid:db"])

    def test_files_fetch_failure_is_reported(self):
        self.write_gh_error("view_files_acme-app_2", "boom")
        code, out, err = self._sync()
        self.assertEqual(code, 1)
        self.assertIn("acme/app#2", err)
        self.assertIn("boom", err)
