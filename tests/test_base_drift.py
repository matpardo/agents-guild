from unittest import mock

from guild import context, db, localbase, paths, timeutil
from guild.commands import board as board_commands
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

    def test_branch_behind_counts_base_commits_missing_from_the_branch(self):
        _git(self.pusher, "push", "origin", "main:feature/x")
        self._push_upstream(2)
        _git(self.repo_dir, "fetch", "origin")
        self.assertEqual(localbase.branch_behind(self.repo_dir, "feature/x", "main"), 2)

    def test_branch_behind_is_none_without_the_branch_ref(self):
        self.assertIsNone(localbase.branch_behind(self.repo_dir, "feature/x", "main"))

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

    def _sync_bases(self):
        return self.run_cli(["sync", "--source", "bases"], "sess-1", self.repo_dir)

    def test_sync_fetches_the_base_and_the_board_shows_the_drift(self):
        before = self._head("main")
        self._merge_upstream("one.txt")
        self._merge_upstream("two.txt")
        with mock.patch("guild.adapters.github._run") as gh_run:
            code, out, err = self._sync_bases()
        self.assertEqual(code, 0, err)
        gh_run.assert_not_called()
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
        code, out, err = self._sync_bases()
        self.assertNotEqual(code, 0)
        self.assertIn("acme/app: base fetch failed", out + err)

    def test_sync_gh_does_not_fetch_the_base(self):
        self._merge_upstream("one.txt")
        self._sync()
        self.assertNotEqual(self._head("origin/main"), _git(self.pusher, "rev-parse", "main"))

    def _board_with_branch_behind(self, behind_commits):
        _git(self.pusher, "push", "origin", "main:feature/x")
        for index in range(behind_commits):
            self._merge_upstream("up{}.txt".format(index))
        self._sync()
        self._sync_bases()
        _git(self.repo_dir, "fetch", "origin", "feature/x")
        return self._board()

    def test_board_shows_how_far_the_pr_branch_is_behind_its_base(self):
        self.assertIn("2 behind main", self._board_with_branch_behind(2))

    def test_board_shows_nothing_for_a_pr_branch_that_is_not_behind(self):
        self.assertNotIn(" behind main", self._board_with_branch_behind(0))

    def test_board_shows_nothing_when_the_pr_branch_ref_is_missing(self):
        self._merge_upstream("one.txt")
        self._sync()
        self._sync_bases()
        self.assertNotIn(" behind main", self._board())

    def test_board_model_carries_the_behind_text(self):
        self._board_with_branch_behind(2)
        conn = db.connect(paths.db_path())
        ctx = context.RunContext(
            conn,
            None,
            None,
            timeutil.utcnow(),
            None,
            paths.claude_sessions_dir(),
            paths.projects_config_dir(),
            paths.state_dir(),
        )
        model = board_commands.board_model(ctx)
        conn.close()
        prs = [
            pr
            for party in model["parties"]
            for quest in party["quests"]
            for task in quest["tasks"]
            for pr in task["prs"]
        ]
        self.assertEqual([pr["behind"] for pr in prs], ["2 behind main"])
