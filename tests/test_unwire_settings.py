import json
import os
from unittest import mock

from guild import claude_settings
from tests.testutil import GuildTestCase


class UnwireSettingsTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.home = self.root / "home"
        self.home.mkdir()
        self.settings_path = self.home / ".claude" / "settings.json"
        self.env = mock.patch.dict(os.environ, {"HOME": str(self.home)})
        self.env.start()
        self.addCleanup(self.env.stop)

    def _settings(self):
        return json.loads(self.settings_path.read_text())

    def _write(self, settings):
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        self.settings_path.write_text(json.dumps(settings))

    def test_wire_then_unwire_keeps_user_entries(self):
        own_hook = {"hooks": [{"type": "command", "command": "my-linter"}]}
        self._write({"model": "opus", "hooks": {"Stop": [own_hook]}, "permissions": {"allow": ["Bash(ls:*)"]}})
        self.run_cli(["wire-settings"], None, None)
        code, out, err = self.run_cli(["unwire-settings"], None, None)
        self.assertEqual(code, 0, err)
        self.assertIn("removed hook Stop: guild hook stop", out)
        self.assertIn("removed ask rule Bash(guild party resume:*)", out)
        self.assertIn("removed allow rule Bash(guild sync:*)", out)
        self.assertEqual(
            self._settings(),
            {"model": "opus", "hooks": {"Stop": [own_hook]}, "permissions": {"allow": ["Bash(ls:*)"]}},
        )

    def test_writes_backup_of_the_wired_file(self):
        self.run_cli(["wire-settings"], None, None)
        wired = self.settings_path.read_bytes()
        self.run_cli(["unwire-settings"], None, None)
        self.assertEqual(self.settings_path.with_name("settings.json.bak").read_bytes(), wired)

    def test_empty_containers_are_dropped(self):
        self.run_cli(["wire-settings"], None, None)
        self.run_cli(["unwire-settings"], None, None)
        self.assertEqual(self._settings(), {})

    def test_removes_retired_and_blanket_rules(self):
        self._write(
            {
                "permissions": {
                    "ask": list(claude_settings.RETIRED_ASK_RULES),
                    "allow": list(claude_settings.BLANKET_ALLOW_RULES),
                }
            }
        )
        code, out, err = self.run_cli(["unwire-settings"], None, None)
        self.assertEqual(code, 0, err)
        self.assertIn("removed ask rule Bash(guild quest add:*)", out)
        self.assertIn("removed allow rule Bash(guild:*)", out)
        self.assertEqual(self._settings(), {})

    def test_second_run_reports_nothing_wired_and_writes_nothing(self):
        self.run_cli(["wire-settings"], None, None)
        self.run_cli(["unwire-settings"], None, None)
        self.settings_path.with_name("settings.json.bak").unlink()
        before = self.settings_path.read_bytes()
        code, out, err = self.run_cli(["unwire-settings"], None, None)
        self.assertEqual(code, 0, err)
        self.assertIn("settings: nothing wired", out)
        self.assertEqual(self.settings_path.read_bytes(), before)
        self.assertFalse(self.settings_path.with_name("settings.json.bak").exists())

    def test_missing_file_is_not_created(self):
        code, out, err = self.run_cli(["unwire-settings"], None, None)
        self.assertEqual(code, 0, err)
        self.assertIn("settings: nothing wired", out)
        self.assertFalse(self.settings_path.exists())
