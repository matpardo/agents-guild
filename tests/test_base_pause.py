import sqlite3

from guild import context, db, paths, timeutil
from guild.commands import board as board_commands
from tests.test_fast_forward_base import _CloneFixture, _git


class BasePauseTests(_CloneFixture):
    def _paused_rows(self):
        conn = sqlite3.connect(str(self.data_home / "guild" / "guild.db"))
        conn.row_factory = sqlite3.Row
        rows = [row["repo"] for row in conn.execute("SELECT repo FROM base_pauses")]
        conn.close()
        return rows

    def _base(self, action, repo, session_id):
        return self.run_cli(["base", action, repo], session_id, self.repo_dir if session_id else None)

    def _sync_bases(self):
        code, out, err = self.run_cli(["sync", "--source", "bases"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)

    def _board(self):
        code, out, err = self.run_cli(["board"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        return out

    def _board_model(self):
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
        return model["bases"]

    def test_human_pauses_and_resumes(self):
        code, out, err = self._base("pause", "acme/app", None)
        self.assertEqual((code, out.strip()), (0, "base of acme/app paused"))
        self.assertEqual(self._paused_rows(), ["acme/app"])
        code, out, err = self._base("resume", "acme/app", None)
        self.assertEqual((code, out.strip()), (0, "base of acme/app resumed"))
        self.assertEqual(self._paused_rows(), [])

    def test_bound_session_pauses(self):
        code, out, err = self._base("pause", "acme/app", "sess-1")
        self.assertEqual(code, 0, err)
        self.assertEqual(self._paused_rows(), ["acme/app"])

    def test_double_pause_is_refused(self):
        self._base("pause", "acme/app", None)
        code, out, err = self._base("pause", "acme/app", None)
        self.assertEqual(code, 1)
        self.assertIn("base of acme/app is already paused", err)

    def test_resume_when_not_paused_is_refused(self):
        code, out, err = self._base("resume", "acme/app", None)
        self.assertEqual(code, 1)
        self.assertIn("base of acme/app is not paused", err)

    def test_unknown_repo_is_refused(self):
        code, out, err = self._base("pause", "acme/other", None)
        self.assertEqual(code, 1)
        self.assertIn("repo 'acme/other' is not in any project", err)

    def test_rebuild_reproduces_pause_and_resume(self):
        self._base("pause", "acme/app", None)
        self.run_cli(["rebuild"], None, None)
        self.assertEqual(self._paused_rows(), ["acme/app"])
        self._base("resume", "acme/app", None)
        self.run_cli(["rebuild"], None, None)
        self.assertEqual(self._paused_rows(), [])

    def test_sync_skips_a_paused_clone_and_fetches_after_resume(self):
        self._base("pause", "acme/app", None)
        before = self._head("origin/main")
        self._merge_upstream("one.txt")
        self._sync_bases()
        self.assertEqual(self._head("origin/main"), before)
        self._base("resume", "acme/app", None)
        self._sync_bases()
        self.assertEqual(self._head("origin/main"), _git(self.pusher, "rev-parse", "main"))

    def test_merged_pr_does_not_fast_forward_a_paused_clone(self):
        self._base("pause", "acme/app", None)
        before = self._head("main")
        self._merge_upstream("one.txt")
        self._merge_prs([1])
        self._sync()
        self.assertEqual(self._head("main"), before)
        self.assertEqual(self._head("origin/main"), before)

    def test_board_marks_a_paused_base_without_warning(self):
        self._merge_upstream("one.txt")
        self._sync_bases()
        self.assertTrue(self._board_model()[0]["warn"])
        self._base("pause", "acme/app", None)
        entry = self._board_model()[0]
        self.assertEqual((entry["paused"], entry["warn"], entry["text"]), (True, False, "acme/app: paused"))
        self.assertIn("acme/app: paused", self._board())
