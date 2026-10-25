import contextlib
import io
import os

from guild.cli import main
from tests.testutil import GuildTestCase


class DeletedCwdTest(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("alpha", ["o/alpha"])
        self.gone = self.repo_dir / "worktree"
        self.gone.mkdir()

    def _whoami_from_deleted_cwd(self):
        original = os.getcwd()
        os.chdir(str(self.gone))
        self.gone.rmdir()
        os.environ["CLAUDE_CODE_SESSION_ID"] = "s-1"
        stdout = io.StringIO()
        stderr = io.StringIO()
        try:
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = main(["whoami"])
        finally:
            os.chdir(original)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_main_falls_back_to_the_nearest_existing_directory(self):
        os.environ["PWD"] = str(self.gone)
        code, out, err = self._whoami_from_deleted_cwd()
        self.assertEqual(code, 0, err)
        self.assertIn("alpha", out)

    def test_main_without_pwd_reports_a_guild_error(self):
        os.environ.pop("PWD", None)
        code, out, err = self._whoami_from_deleted_cwd()
        self.assertNotEqual(code, 0)
        self.assertIn("guild:", err)

    def test_hook_falls_back_when_stdin_cwd_was_deleted(self):
        self.gone.rmdir()
        code, out, err = self.run_hook("session-start", {"session_id": "s-1", "cwd": str(self.gone)})
        self.assertEqual(code, 0)
        self.assertNotIn("guild hook error", out)
