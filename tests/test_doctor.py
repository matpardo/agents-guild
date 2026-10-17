import json
import os
from unittest import mock

from guild import paths
from guild.commands import statusline as statusline_commands
from tests.testutil import GuildTestCase

_ALL_HOOKS = {
    "SessionStart": [{"hooks": [{"type": "command", "command": "guild hook session-start"}]}],
    "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "guild hook prompt-submit"}]}],
    "PostToolUse": [{"hooks": [{"type": "command", "command": "guild hook post-tool-use"}]}],
    "Notification": [{"hooks": [{"type": "command", "command": "guild hook notification"}]}],
    "Stop": [{"hooks": [{"type": "command", "command": "guild hook stop"}]}],
    "PreToolUse": [
        {"matcher": "Bash", "hooks": [{"type": "command", "command": "guild hook pre-push"}]},
        {"matcher": "Edit|Write", "hooks": [{"type": "command", "command": "guild hook pre-edit"}]},
        {"matcher": "Bash", "hooks": [{"type": "command", "command": "guild hook pre-pr-owner"}]},
        {"matcher": "Bash", "hooks": [{"type": "command", "command": "guild hook pre-answer"}]},
    ],
}

_ASK_RULES = ["Bash(guild party start:*)", "Bash(guild quest add:*)"]

_ALLOW_RULES = [
    "Bash(guild task:*)",
    "Bash(guild pr:*)",
    "Bash(guild finding:*)",
    "Bash(guild notice:*)",
    "Bash(guild ask:*)",
    "Bash(guild next:*)",
    "Bash(guild claim:*)",
    "Bash(guild release:*)",
    "Bash(guild raid:*)",
    "Bash(guild handoff:*)",
    "Bash(guild sync:*)",
    "Bash(guild memory:*)",
]


class DoctorTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.home = self.root / "home"
        (self.home / ".claude").mkdir(parents=True)
        self.env = mock.patch.dict(os.environ, {"HOME": str(self.home)})
        self.env.start()
        self.addCleanup(self.env.stop)

    def _write_settings(self, hooks):
        self._write_full_settings(hooks, _ASK_RULES, _ALLOW_RULES)

    def _write_full_settings(self, hooks, ask_rules, allow_rules):
        settings = {"hooks": hooks, "permissions": {"ask": ask_rules, "allow": allow_rules}}
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
        self._write_full_settings(_ALL_HOOKS, ["Bash(guild quest add:*)"], _ALLOW_RULES)
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
        self.assertEqual(out.count("missing hook"), 9)
        self.assertEqual(out.count("missing ask rule"), 2)

    def test_missing_notification_and_stop_hooks_fail_and_name_them(self):
        hooks = dict(_ALL_HOOKS)
        del hooks["Notification"]
        del hooks["Stop"]
        self._write_settings(hooks)
        self._link_rules()
        code, out, err = self.run_cli(["doctor"], None, None)
        self.assertEqual(code, 1)
        self.assertIn("missing hook Notification: guild hook notification", out)
        self.assertIn("missing hook Stop: guild hook stop", out)

    def test_wired_notification_and_stop_hooks_pass(self):
        self._write_settings(_ALL_HOOKS)
        self._link_rules()
        code, out, err = self.run_cli(["doctor"], None, None)
        self.assertIn("ok      hook Notification: guild hook notification", out)
        self.assertIn("ok      hook Stop: guild hook stop", out)

    def test_allow_rules_present_are_ok(self):
        self._write_settings(_ALL_HOOKS)
        self._link_rules()
        code, out, err = self.run_cli(["doctor"], None, None)
        self.assertEqual(code, 0, out)
        self.assertIn("ok      allow rule Bash(guild task:*)", out)
        self.assertEqual(out.count("ok      allow rule"), len(_ALLOW_RULES))

    def test_missing_allow_rule_warns_without_changing_exit(self):
        self._write_full_settings(_ALL_HOOKS, _ASK_RULES, ["Bash(guild task:*)"])
        self._link_rules()
        code, out, err = self.run_cli(["doctor"], None, None)
        self.assertEqual(code, 0, out)
        self.assertIn(
            "warn    allow rule missing Bash(guild pr:*) (a permission prompt can stall the session)", out
        )
        self.assertIn("ok      allow rule Bash(guild task:*)", out)

    def test_settings_without_allow_list_warns_for_every_rule(self):
        (self.home / ".claude" / "settings.json").write_text(
            json.dumps({"hooks": _ALL_HOOKS, "permissions": {"ask": _ASK_RULES}})
        )
        self._link_rules()
        code, out, err = self.run_cli(["doctor"], None, None)
        self.assertEqual(code, 0, out)
        self.assertEqual(out.count("warn    allow rule missing"), len(_ALLOW_RULES))

    def test_blanket_guild_allow_satisfies_every_rule(self):
        for blanket in ("Bash(guild:*)", "Bash(guild *)"):
            with self.subTest(blanket=blanket):
                self._write_full_settings(_ALL_HOOKS, _ASK_RULES, [blanket])
                self._link_rules()
                code, out, err = self.run_cli(["doctor"], None, None)
                self.assertEqual(code, 0, out)
                self.assertEqual(out.count("ok      allow rule"), len(_ALLOW_RULES))
                self.assertNotIn("allow rule missing", out)

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

    def _clipboard_doctor_out(self, tools):
        self._write_settings(_ALL_HOOKS)
        self._link_rules()
        which = lambda name: "/bin/" + name if name in tools else None
        with mock.patch.dict(os.environ, {"DISPLAY": ":0"}), mock.patch(
            "guild.tmux_windows.shutil.which", side_effect=which
        ):
            _, out, _ = self.run_cli(["doctor"], None, None)
        return out

    def test_warns_when_tmux_has_no_clipboard_tool(self):
        out = self._clipboard_doctor_out({"tmux"})
        self.assertIn(
            "warn    tmux copy reaches the clipboard only through the terminal (OSC 52): "
            "install xclip (X11) or wl-clipboard (Wayland)",
            out,
        )

    def test_no_clipboard_warning_when_tool_found(self):
        self.assertNotIn("OSC 52", self._clipboard_doctor_out({"tmux", "xclip"}))

    def test_no_clipboard_warning_without_tmux(self):
        self.assertNotIn("OSC 52", self._clipboard_doctor_out(set()))

    def _doctor_out_for_clean_setup(self):
        self._write_settings(_ALL_HOOKS)
        self._link_rules()
        _, out, _ = self.run_cli(["doctor"], None, None)
        return out

    def test_warns_on_leftover_dispatcher_unit_file(self):
        unit_dir = self.config_home / "systemd" / "user"
        unit_dir.mkdir(parents=True)
        (unit_dir / "guild-dispatch.timer").write_text("")
        out = self._doctor_out_for_clean_setup()
        self.assertIn("warn    {}".format(unit_dir / "guild-dispatch.timer"), out)
        self.assertNotIn("guild-dispatch.service", out)

    def test_no_unit_warning_without_leftover(self):
        self.assertNotIn("retired dispatcher", self._doctor_out_for_clean_setup())

    def test_warns_on_project_config_with_dispatcher_key(self):
        self.register_project("acme", ["acme/app"])
        path = self.config_home / "guild" / "projects" / "acme.json"
        data = json.loads(path.read_text())
        data["dispatcher"] = {"rules": {"next_task": "on"}}
        path.write_text(json.dumps(data))
        out = self._doctor_out_for_clean_setup()
        self.assertIn("ok      project acme", out)
        self.assertIn("warn    project acme still has a 'dispatcher' key", out)

    def test_warns_when_threshold_is_above_observed_compaction(self):
        self.register_project("acme", ["acme/app"])
        statusline_commands.record_compact_pct(paths.state_dir(), "acme", 31)
        statusline_commands.record_compact_pct(paths.state_dir(), "acme", 24)
        out = self._doctor_out_for_clean_setup()
        self.assertIn(
            "warn    project acme handoff_threshold 80% is above observed compaction at 24% (2 samples): lower it below 24",
            out,
        )

    def test_no_compaction_warning_when_threshold_is_below_it(self):
        self.register_project("acme", ["acme/app"])
        path = self.config_home / "guild" / "projects" / "acme.json"
        data = json.loads(path.read_text())
        data["handoff_threshold"] = 20
        path.write_text(json.dumps(data))
        statusline_commands.record_compact_pct(paths.state_dir(), "acme", 24)
        self.assertNotIn("observed compaction", self._doctor_out_for_clean_setup())

    def test_no_compaction_warning_without_samples(self):
        self.register_project("acme", ["acme/app"])
        self.assertNotIn("observed compaction", self._doctor_out_for_clean_setup())
