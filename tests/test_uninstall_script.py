import os
import subprocess
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = _REPO_ROOT / "uninstall.sh"


class UninstallScriptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.link = self.home / ".local" / "bin" / "guild"
        self.guild_md = self.home / ".claude" / "GUILD.md"
        self.data_dirs = [
            self.home / ".local" / "share" / "guild",
            self.home / ".config" / "guild",
            self.home / ".local" / "state" / "guild",
        ]

    def _run(self, *args):
        env = dict(os.environ, HOME=str(self.home))
        for name in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME"):
            env.pop(name, None)
        return subprocess.run(["bash", str(_SCRIPT), *args], capture_output=True, text=True, env=env)

    def _install_links(self):
        self.link.parent.mkdir(parents=True)
        self.link.symlink_to(_REPO_ROOT / "bin" / "guild")
        self.guild_md.parent.mkdir(parents=True, exist_ok=True)
        self.guild_md.symlink_to(_REPO_ROOT / "GUILD.md")

    def _make_data(self):
        for directory in self.data_dirs:
            directory.mkdir(parents=True)
            (directory / "file").write_text("x")

    def test_removes_symlinks_to_the_repo(self):
        self._install_links()
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.link.is_symlink())
        self.assertFalse(self.guild_md.is_symlink())

    def test_foreign_file_is_left_with_warning(self):
        self.link.parent.mkdir(parents=True)
        self.link.write_text("mine")
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.link.read_text(), "mine")
        self.assertIn("WARN: {} is not a symlink".format(self.link), result.stdout)

    def test_default_keeps_data(self):
        self._make_data()
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stderr)
        for directory in self.data_dirs:
            self.assertTrue(directory.exists())
            self.assertIn("kept data: {}".format(directory), result.stdout)
        self.assertIn("rerun with --purge", result.stdout)

    def test_purge_removes_data(self):
        self._make_data()
        result = self._run("--purge")
        self.assertEqual(result.returncode, 0, result.stderr)
        for directory in self.data_dirs:
            self.assertFalse(directory.exists())
            self.assertIn("deleted {}".format(directory), result.stdout)

    def test_bad_argument_prints_usage(self):
        result = self._run("--nope")
        self.assertEqual(result.returncode, 2)
        self.assertIn("usage: ./uninstall.sh", result.stdout)

    def test_claude_md_leftover_hint(self):
        self.guild_md.parent.mkdir(parents=True)
        (self.home / ".claude" / "CLAUDE.md").write_text("@~/.claude/GUILD.md\n")
        result = self._run()
        self.assertIn("remove the line @~/.claude/GUILD.md", result.stdout)
        self.assertIn("guild hook pre-commit", result.stdout)

    def test_no_claude_md_hint_without_the_line(self):
        result = self._run()
        self.assertNotIn("remove the line @~/.claude/GUILD.md", result.stdout)


if __name__ == "__main__":
    unittest.main()
