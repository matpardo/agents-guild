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
        self.fake_bin = self.home / "fake-bin"
        self.fake_bin.mkdir()
        self.systemctl_log = self.home / "systemctl.log"
        fake = self.fake_bin / "systemctl"
        fake.write_text('#!/bin/sh\necho "$@" >> "{}"\n'.format(self.systemctl_log))
        fake.chmod(0o755)
        self.unit_dir = self.home / ".config" / "systemd" / "user"

    def _run(self):
        env = dict(os.environ, HOME=str(self.home), PATH="{}:{}".format(self.fake_bin, os.environ["PATH"]))
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

    def test_removes_retired_dispatcher_timer(self):
        self.unit_dir.mkdir(parents=True)
        (self.unit_dir / "guild-dispatch.timer").write_text("")
        (self.unit_dir / "guild-dispatch.service").write_text("")
        (self.unit_dir / "guild-sync-gh.timer").write_text("")
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.unit_dir / "guild-dispatch.timer").exists())
        self.assertFalse((self.unit_dir / "guild-dispatch.service").exists())
        self.assertTrue((self.unit_dir / "guild-sync-gh.timer").exists())
        self.assertEqual(
            self.systemctl_log.read_text().splitlines(),
            ["--user disable --now guild-dispatch.timer", "--user daemon-reload"],
        )
        self.assertIn("removed the retired dispatcher timer", result.stdout)

    def test_leaves_systemd_alone_without_retired_timer(self):
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.systemctl_log.exists())
        self.assertNotIn("retired dispatcher", result.stdout)

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
