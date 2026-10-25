import os
import subprocess
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = _REPO_ROOT / "timers.sh"


class TimersScriptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.fake_bin = self.home / "fake-bin"
        self.fake_bin.mkdir()
        self.guild_log = self.home / "guild.log"
        fake = self.fake_bin / "guild"
        fake.write_text('#!/bin/sh\necho "$@" >> "{}"\n'.format(self.guild_log))
        fake.chmod(0o755)
        systemctl = self.fake_bin / "systemctl"
        systemctl.write_text("#!/bin/sh\n")
        systemctl.chmod(0o755)
        self.unit_dir = self.home / ".config" / "systemd" / "user"

    def _run(self, path):
        env = dict(os.environ, HOME=str(self.home), PATH=path)
        env.pop("XDG_CONFIG_HOME", None)
        return subprocess.run(["bash", str(_SCRIPT)], capture_output=True, text=True, env=env)

    def _run_with_fakes(self):
        return self._run("{}:{}".format(self.fake_bin, os.environ["PATH"]))

    def test_installs_every_timer_with_its_default_interval(self):
        result = self._run_with_fakes()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self.guild_log.read_text().splitlines(),
            [
                "sync-timer install --every 10m",
                "sync-sdd-timer install --every 10m",
                "sync-tracker-timer install --every 10m",
                "sync-bases-timer install --every 1m",
                "resources-timer install --every 2h",
                "compact-timer install --every 1d",
            ],
        )

    def test_keeps_the_interval_of_an_installed_timer(self):
        self.unit_dir.mkdir(parents=True)
        (self.unit_dir / "guild-sync-gh.timer").write_text("[Timer]\nOnUnitActiveSec=300s\n")
        (self.unit_dir / "guild-compact.timer").write_text("[Timer]\nOnUnitActiveSec=172800s\n")
        (self.unit_dir / "guild-resources-collect.timer").write_text("[Timer]\nOnUnitActiveSec=5400s\n")
        self._run_with_fakes()
        lines = self.guild_log.read_text().splitlines()
        self.assertIn("sync-timer install --every 5m", lines)
        self.assertIn("compact-timer install --every 2d", lines)
        self.assertIn("resources-timer install --every 90m", lines)

    def test_skips_without_systemctl(self):
        bare = self.home / "bare-bin"
        bare.mkdir()
        for tool in ("bash", "sed", "dirname"):
            (bare / tool).symlink_to(subprocess.check_output(["which", tool], text=True).strip())
        result = self._run(str(bare))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("systemctl not found", result.stdout)
        self.assertFalse(self.guild_log.exists())
