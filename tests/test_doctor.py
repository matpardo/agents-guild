import json
import os
from unittest import mock

from tests.testutil import GuildTestCase

_ALL_HOOKS = {
    "SessionStart": [{"hooks": [{"type": "command", "command": "guild hook session-start"}]}],
    "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "guild hook prompt-submit"}]}],
    "PostToolUse": [{"hooks": [{"type": "command", "command": "guild hook post-tool-use"}]}],
    "PreToolUse": [
        {"matcher": "Bash", "hooks": [{"type": "command", "command": "guild hook pre-push"}]},
        {"matcher": "Edit|Write", "hooks": [{"type": "command", "command": "guild hook pre-edit"}]},
    ],
}

_ASK_RULES = ["Bash(guild party start:*)", "Bash(guild quest add:*)"]


class DoctorTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.home = self.root / "home"
        (self.home / ".claude").mkdir(parents=True)
        self.env = mock.patch.dict(os.environ, {"HOME": str(self.home)})
        self.env.start()
        self.addCleanup(self.env.stop)

    def _write_settings(self, hooks):
        self._write_full_settings(hooks, _ASK_RULES)

    def _write_full_settings(self, hooks, ask_rules):
        settings = {"hooks": hooks, "permissions": {"ask": ask_rules}}
        (self.home / ".claude" / "settings.json").write_text(json.dumps(settings))

    def _link_rules(self):
        (self.home / ".claude" / "GUILD.md").write_text("rules")

    def test_everything_wired_passes(self):
        self._write_settings(_ALL_HOOKS)
        self._link_rules()
        self.register_project("acme", ["acme/app"])
        code, out, err = self.run_cli(["doctor"], None, None)
        self.assertEqual(code, 0, out + err)
        self.assertIn("ok      hook SessionStart: guild hook session-start", out)
        self.assertIn("ok      project acme", out)
        self.assertIn("ok      ask rule Bash(guild party start:*)", out)
        self.assertNotIn("missing", out)

    def test_missing_ask_rule_fails_and_names_it(self):
        self._write_full_settings(_ALL_HOOKS, ["Bash(guild quest add:*)"])
        self._link_rules()
        code, out, err = self.run_cli(["doctor"], None, None)
        self.assertEqual(code, 1)
        self.assertIn("missing ask rule Bash(guild party start:*)", out)
        self.assertIn("ok      ask rule Bash(guild quest add:*)", out)

    def test_settings_without_permissions_reports_both_ask_rules(self):
        (self.home / ".claude" / "settings.json").write_text(json.dumps({"hooks": _ALL_HOOKS}))
        self._link_rules()
        code, out, err = self.run_cli(["doctor"], None, None)
        self.assertEqual(code, 1)
        self.assertEqual(out.count("missing ask rule"), 2)

    def test_missing_hook_fails_and_names_it(self):
        hooks = dict(_ALL_HOOKS)
        del hooks["PostToolUse"]
        self._write_settings(hooks)
        self._link_rules()
        code, out, err = self.run_cli(["doctor"], None, None)
        self.assertEqual(code, 1)
        self.assertIn("missing hook PostToolUse: guild hook post-tool-use", out)

    def test_missing_settings_file_reports_every_hook(self):
        self._link_rules()
        code, out, err = self.run_cli(["doctor"], None, None)
        self.assertEqual(code, 1)
        self.assertEqual(out.count("missing hook"), 5)
        self.assertEqual(out.count("missing ask rule"), 2)

    def test_missing_rules_link_fails(self):
        self._write_settings(_ALL_HOOKS)
        code, out, err = self.run_cli(["doctor"], None, None)
        self.assertEqual(code, 1)
        self.assertIn("missing ~/.claude/GUILD.md", out)

    def test_invalid_project_config_is_reported_without_stopping(self):
        self._write_settings(_ALL_HOOKS)
        self._link_rules()
        self.register_project("acme", ["acme/app"])
        projects_dir = self.config_home / "guild" / "projects"
        (projects_dir / "broken.json").write_text("{not json")
        code, out, err = self.run_cli(["doctor"], None, None)
        self.assertEqual(code, 1)
        self.assertIn("ok      project acme", out)
        self.assertIn("invalid project broken.json", out)
