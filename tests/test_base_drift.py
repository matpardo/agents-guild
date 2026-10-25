from guild import localbase
from tests.test_fast_forward_base import _CloneFixture, _git


class BaseDriftTests(_CloneFixture):
    def _project(self):
        return {"paths": [str(self.repo_dir)], "github": {"repos": ["acme/app"]}}

    def _drift(self):
        return localbase.base_drift(self._project())

    def _push_upstream(self, count):
        for index in range(count):
            self._merge_upstream("up{}.txt".format(index))

    def test_never_fetched_clone_is_up_to_date_with_no_fetch_time(self):
        self._push_upstream(2)
        self.assertEqual(
            self._drift(),
            [{"repo": "acme/app", "base": "main", "behind": 0, "ahead": 0, "fetched_at": None, "error": None}],
        )

    def test_fetch_makes_the_clone_behind_by_the_upstream_commits(self):
        self._push_upstream(2)
        self.assertIsNone(localbase.fetch_base_mutating_git(self.repo_dir, "main"))
        entry = self._drift()[0]
        self.assertEqual((entry["behind"], entry["ahead"]), (2, 0))
        self.assertIsNotNone(entry["fetched_at"])

    def test_local_commits_count_as_ahead(self):
        self._commit(self.repo_dir, "local.txt", "local")
        self._push_upstream(1)
        localbase.fetch_base_mutating_git(self.repo_dir, "main")
        entry = self._drift()[0]
        self.assertEqual((entry["behind"], entry["ahead"]), (1, 1))

    def test_clone_without_origin_head_reports_the_error(self):
        _git(self.repo_dir, "remote", "set-head", "origin", "-d")
        self.assertEqual(
            self._drift(),
            [
                {
                    "repo": "acme/app",
                    "base": None,
                    "behind": None,
                    "ahead": None,
                    "fetched_at": None,
                    "error": "no origin/HEAD (git remote set-head origin --auto)",
                }
            ],
        )

    def test_clone_whose_base_cannot_be_compared_reports_the_error(self):
        _git(self.repo_dir, "update-ref", "-d", "refs/remotes/origin/main")
        entry = self._drift()[0]
        self.assertEqual((entry["base"], entry["error"]), ("main", "cannot compare"))

    def test_parent_directory_path_finds_the_clones_inside(self):
        project = {"paths": [str(self.repo_dir.parent)], "github": {"repos": ["acme/app"]}}
        self.assertEqual([clone["repo"] for clone in localbase.locate_clones(project)], ["acme/app"])

    def test_warning_lines_reuse_the_drift(self):
        self._push_upstream(2)
        localbase.fetch_base_mutating_git(self.repo_dir, "main")
        self.assertEqual(
            localbase.behind_warning_lines(self._project()), ["local main of acme/app is 2 commits behind origin/main"]
        )


class BaseDriftSyncAndBoardTests(_CloneFixture):
    def _board(self):
        code, out, err = self.run_cli(["board"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        return out

    def test_board_shows_up_to_date_and_never_fetched_before_a_sync(self):
        self.assertIn("acme/app main: up to date (never fetched)", self._board())

    def test_sync_fetches_the_base_and_the_board_shows_the_drift(self):
        before = self._head("main")
        self._merge_upstream("one.txt")
        self._merge_upstream("two.txt")
        self._sync()
        self.assertEqual(self._head("main"), before)
        self.assertEqual(self._head("origin/main"), _git(self.pusher, "rev-parse", "main"))
        self.assertIn("acme/app main: 2 behind (fetched 0s ago)", self._board())

    def test_board_shows_a_clone_without_origin_head(self):
        _git(self.repo_dir, "remote", "set-head", "origin", "-d")
        self.assertIn("acme/app: no origin/HEAD (git remote set-head origin --auto)", self._board())

    def test_board_shows_ahead_commits(self):
        self._commit(self.repo_dir, "local.txt", "local")
        self.assertIn("acme/app main: 0 behind, 1 ahead (never fetched)", self._board())

    def test_fetch_failure_is_reported_as_a_sync_failure(self):
        self.remote.rename(self.remote.with_name("gone.git"))
        code, out, err = self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)
        self.assertIn("acme/app: base fetch failed", out + err)
