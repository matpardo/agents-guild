import contextlib
import io
import subprocess
import tempfile
import unittest
from pathlib import Path

from guild import cli, version


def _git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo)] + list(args), check=True, capture_output=True, text=True
    ).stdout.strip()


class DescribeTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        _git(self.repo, "init", "-q")
        _git(self.repo, "config", "user.email", "dev@example.com")
        _git(self.repo, "config", "user.name", "dev")
        self._commit("first")

    def tearDown(self):
        self._tmp.cleanup()

    def _commit(self, text):
        (self.repo / "file.txt").write_text(text)
        _git(self.repo, "add", "file.txt")
        _git(self.repo, "commit", "-q", "-m", text)

    def test_untagged_repo_reports_the_short_commit(self):
        self.assertEqual(version.describe(self.repo), _git(self.repo, "rev-parse", "--short", "HEAD"))

    def test_tagged_head_reports_the_tag(self):
        _git(self.repo, "tag", "-a", "v0.1.0", "-m", "v0.1.0")
        self.assertEqual(version.describe(self.repo), "v0.1.0")

    def test_commits_after_the_tag_are_counted(self):
        _git(self.repo, "tag", "-a", "v0.1.0", "-m", "v0.1.0")
        self._commit("second")
        sha = _git(self.repo, "rev-parse", "--short", "HEAD")
        self.assertEqual(version.describe(self.repo), "v0.1.0-1-g{}".format(sha))

    def test_uncommitted_changes_are_marked_dirty(self):
        _git(self.repo, "tag", "-a", "v0.1.0", "-m", "v0.1.0")
        (self.repo / "file.txt").write_text("changed")
        self.assertEqual(version.describe(self.repo), "v0.1.0-dirty")

    def test_a_folder_outside_git_reports_unknown(self):
        with tempfile.TemporaryDirectory() as plain:
            self.assertEqual(version.describe(Path(plain)), "unknown")


class CliVersionTest(unittest.TestCase):
    def test_version_flag_prints_the_version_and_exits_zero(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main(["--version"])
        self.assertEqual(code, 0)
        self.assertRegex(out.getvalue(), r"^guild \S+\n$")


if __name__ == "__main__":
    unittest.main()
