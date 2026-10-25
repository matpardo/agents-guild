import json
import os
from unittest import mock

from guild import claude_settings
from tests.testutil import GuildTestCase


class WireSettingsTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.home = self.root / "home"
        self.home.mkdir()
        self.settings_path = self.home / ".claude" / "settings.json"
        self.env = mock.patch.dict(os.environ, {"HOME": str(self.home)})
        self.env.start()
        self.addCleanup(self.env.stop)

    def _wire(self):
        code, out, err = self.run_cli(["wire-settings"], None, None)
        return code, out, err

    def _settings(self):
        return json.loads(self.settings_path.read_text())

    def _write(self, settings):
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        self.settings_path.write_text(json.dumps(settings))

    def test_missing_file_is_created_with_everything(self):
        code, out, err = self._wire()
        self.assertEqual(code, 0, err)
        settings = self._settings()
        self.assertIn("added hook PreToolUse: guild hook pre-edit", out)
        self.assertIn("added ask rule Bash(guild party resume:*)", out)
        self.assertIn("added allow rule Bash(guild sync:*)", out)
        self.assertEqual(settings["permissions"]["ask"], list(claude_settings.EXPECTED_ASK_RULES))
        self.assertEqual(settings["permissions"]["allow"], list(claude_settings.EXPECTED_ALLOW_RULES))
        self.assertEqual(
            settings["hooks"]["PreToolUse"][1],
            {
                "matcher": "Edit|Write|MultiEdit|NotebookEdit",
                "hooks": [{"type": "command", "command": "guild hook pre-edit"}],
            },
        )
        self.assertEqual(settings["hooks"]["Stop"], [{"hooks": [{"type": "command", "command": "guild hook stop"}]}])
        self.assertTrue(self.settings_path.read_text().endswith("}\n"))
        self.assertFalse(self.settings_path.with_name("settings.json.bak").exists())

    def test_partial_file_keeps_foreign_keys_and_entries(self):
        foreign_hook = {"matcher": "Bash", "hooks": [{"type": "command", "command": "other-tool"}]}
        self._write(
            {
                "theme": "dark",
                "hooks": {
                    "PreToolUse": [foreign_hook],
                    "Stop": [{"hooks": [{"type": "command", "command": "/opt/bin/guild hook stop"}]}],
                },
                "permissions": {"allow": ["Bash(ls:*)"], "deny": ["Bash(rm:*)"]},
            }
        )
        code, out, err = self._wire()
        self.assertEqual(code, 0, err)
        settings = self._settings()
        self.assertEqual(settings["theme"], "dark")
        self.assertEqual(settings["permissions"]["deny"], ["Bash(rm:*)"])
        self.assertEqual(settings["permissions"]["allow"][0], "Bash(ls:*)")
        self.assertEqual(settings["hooks"]["PreToolUse"][0], foreign_hook)
        self.assertEqual(len(settings["hooks"]["PreToolUse"]), 5)
        self.assertEqual(len(settings["hooks"]["Stop"]), 1)
        self.assertNotIn("hook Stop", out)

    def test_backup_holds_original_bytes(self):
        self.settings_path.parent.mkdir(parents=True)
        original = '{"theme":   "dark"}'
        self.settings_path.write_text(original)
        self._wire()
        backup = self.settings_path.with_name("settings.json.bak")
        self.assertEqual(backup.read_text(), original)

    def test_second_run_writes_nothing(self):
        self._wire()
        before = self.settings_path.read_bytes()
        self.settings_path.with_name("settings.json.bak").unlink(missing_ok=True)
        code, out, err = self._wire()
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "settings: already wired ({})".format(self.settings_path))
        self.assertEqual(self.settings_path.read_bytes(), before)
        self.assertFalse(self.settings_path.with_name("settings.json.bak").exists())

    def test_blanket_allow_rule_is_respected(self):
        self._write({"permissions": {"allow": ["Bash(guild:*)"]}})
        self._wire()
        self.assertEqual(self._settings()["permissions"]["allow"], ["Bash(guild:*)"])

    def test_retired_ask_rule_is_removed(self):
        self._write({"permissions": {"ask": ["Bash(guild quest add:*)", "Bash(other:*)"]}})
        code, out, err = self._wire()
        self.assertEqual(code, 0, err)
        self.assertIn("removed ask rule Bash(guild quest add:*)", out)
        ask = self._settings()["permissions"]["ask"]
        self.assertNotIn("Bash(guild quest add:*)", ask)
        self.assertEqual(ask[0], "Bash(other:*)")

    def test_retired_start_ask_rules_are_removed(self):
        self._write({"permissions": {"ask": ["Bash(guild party start:*)", "Bash(guild adventurer start:*)"]}})
        code, out, err = self._wire()
        self.assertEqual(code, 0, err)
        self.assertIn("removed ask rule Bash(guild party start:*)", out)
        self.assertIn("removed ask rule Bash(guild adventurer start:*)", out)
        ask = self._settings()["permissions"]["ask"]
        self.assertNotIn("Bash(guild party start:*)", ask)
        self.assertNotIn("Bash(guild adventurer start:*)", ask)

    def test_binding_commands_ask_and_quest_add_is_allowed(self):
        self._wire()
        permissions = self._settings()["permissions"]
        for rule in (
            "Bash(guild party resume:*)",
            "Bash(guild raid join:*)",
        ):
            self.assertIn(rule, permissions["ask"])
        for rule in ("Bash(guild party start:*)", "Bash(guild adventurer start:*)"):
            self.assertNotIn(rule, permissions["ask"])
        self.assertIn("Bash(guild party:*)", permissions["allow"])
        self.assertIn("Bash(guild quest:*)", permissions["allow"])
        self.assertNotIn("Bash(guild quest add:*)", permissions["ask"])

    def test_invalid_json_is_refused_and_left_untouched(self):
        self.settings_path.parent.mkdir(parents=True)
        self.settings_path.write_text("{not json")
        code, out, err = self._wire()
        self.assertEqual(code, 1)
        self.assertIn("invalid JSON", err)
        self.assertEqual(self.settings_path.read_text(), "{not json")
        self.assertFalse(self.settings_path.with_name("settings.json.bak").exists())

    def test_doctor_is_healthy_after_wiring(self):
        self._wire()
        (self.home / ".claude" / "GUILD.md").write_text("rules")
        (self.config_home / "guild").mkdir(parents=True, exist_ok=True)
        (self.config_home / "guild" / "guild.json").write_text('{"name": "forge"}')
        with mock.patch("guild.commands.doctor.shutil.which", return_value=None):
            code, out, err = self.run_cli(["doctor"], None, None)
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("missing", out)
        self.assertNotIn("warn", out)
