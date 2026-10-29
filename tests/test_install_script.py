import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = _REPO_ROOT / "install.sh"


class InstallScriptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)

    def _run(self):
        env = dict(os.environ, HOME=str(self.home))
        env.pop("XDG_CONFIG_HOME", None)
        return subprocess.run(["bash", str(_SCRIPT)], capture_output=True, text=True, env=env)

    def test_links_and_wires_settings(self):
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.home / ".local" / "bin" / "guild").resolve(), _REPO_ROOT / "bin" / "guild")
        self.assertEqual((self.home / ".claude" / "GUILD.md").resolve(), _REPO_ROOT / "GUILD.md")
        settings = json.loads((self.home / ".claude" / "settings.json").read_text())
        self.assertIn("SessionStart", settings["hooks"])
        self.assertIn("Bash(guild party resume:*)", settings["permissions"]["ask"])
        self.assertIn("added hook Stop: guild hook stop", result.stdout)

    def test_rerun_reports_already_wired(self):
        self._run()
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("settings: already wired", result.stdout)

    def test_hints_the_claude_md_line_when_missing(self):
        result = self._run()
        self.assertIn("add the line @~/.claude/GUILD.md", result.stdout)

    def test_no_claude_md_hint_when_the_line_is_there(self):
        target = self.home / "configs" / "CLAUDE.md"
        target.parent.mkdir()
        target.write_text("# rules\n@~/.claude/GUILD.md\n")
        (self.home / ".claude").mkdir()
        (self.home / ".claude" / "CLAUDE.md").symlink_to(target)
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("add the line @~/.claude/GUILD.md", result.stdout)
