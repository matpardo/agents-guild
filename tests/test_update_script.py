import os
import subprocess
import tempfile
import unittest
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parent.parent / "update.sh"


def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True).stdout


class UpdateScriptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.home = root / "home"
        self.home.mkdir()
        self.dev = root / "dev"
        self.dev.mkdir()
        _git(self.dev, "init", "-q", "-b", "main")
        _git(self.dev, "config", "user.email", "t@t.com")
        _git(self.dev, "config", "user.name", "t")
        (self.dev / "install.sh").write_text("#!/usr/bin/env bash\necho installed\n")
        (self.dev / "bin").mkdir()
        (self.dev / "bin" / "guild").write_text("#!/usr/bin/env bash\necho \"doctor says ${DOCTOR_EXIT:-0}\"\nexit ${DOCTOR_EXIT:-0}\n")
        os.chmod(self.dev / "install.sh", 0o755)
        os.chmod(self.dev / "bin" / "guild", 0o755)
        _git(self.dev, "add", "-A")
        _git(self.dev, "commit", "-q", "-m", "first")
        self.origin = root / "origin.git"
        _git(root, "clone", "-q", "--bare", str(self.dev), str(self.origin))
        _git(self.dev, "remote", "add", "origin", str(self.origin))
        _git(self.dev, "fetch", "-q", "origin")
        self.live = root / "live"
        _git(self.dev, "worktree", "add", "-q", "--detach", str(self.live), "origin/main")
        (self.dev / "feature.txt").write_text("new")
        _git(self.dev, "add", "-A")
        _git(self.dev, "commit", "-q", "-m", "feat: second")
        _git(self.dev, "push", "-q", "origin", "main")

    def _run(self, args, doctor_exit):
        env = dict(os.environ, HOME=str(self.home), DOCTOR_EXIT=str(doctor_exit))
        return subprocess.run(["bash", str(_SCRIPT), *args], capture_output=True, text=True, env=env)

    def test_moves_installed_worktree_to_origin_main_and_lists_changes(self):
        result = self._run([str(self.live)], 0)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(_git(self.live, "rev-parse", "HEAD"), _git(self.dev, "rev-parse", "origin/main"))
        self.assertIn("feat: second", result.stdout)
        self.assertIn("installed", result.stdout)
        self.assertIn("doctor says 0", result.stdout)

    def test_already_up_to_date_is_reported(self):
        self._run([str(self.live)], 0)
        result = self._run([str(self.live)], 0)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("already at", result.stdout)

    def test_refuses_a_dirty_worktree(self):
        (self.live / "local.txt").write_text("edit")
        before = _git(self.live, "rev-parse", "HEAD")
        result = self._run([str(self.live)], 0)
        self.assertEqual(result.returncode, 1)
        self.assertIn("has local changes", result.stdout + result.stderr)
        self.assertEqual(_git(self.live, "rev-parse", "HEAD"), before)

    def test_doctor_findings_are_shown_without_failing_the_update(self):
        result = self._run([str(self.live)], 1)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("need attention", result.stdout)

    def test_requires_the_installed_worktree_argument(self):
        result = self._run([], 0)
        self.assertEqual(result.returncode, 2)
        self.assertIn("usage", result.stdout + result.stderr)

    def test_rejects_a_path_that_is_not_a_git_checkout(self):
        result = self._run([str(self.home)], 0)
        self.assertEqual(result.returncode, 1)
        self.assertIn("is not a git checkout", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
