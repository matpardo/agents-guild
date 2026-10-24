import json
import os
from unittest import mock

from guild import claude_settings, paths
from guild.commands import statusline as statusline_commands
from tests.testutil import GuildTestCase

_ALL_HOOKS = {
    "SessionStart": [{"hooks": [{"type": "command", "command": "guild hook session-start"}]}],
    "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "guild hook prompt-submit"}]}],
    "PostToolUse": [{"hooks": [{"type": "command", "command": "guild hook post-tool-use"}]}],
    "Notification": [{"hooks": [{"type": "command", "command": "guild hook notification"}]}],
    "Stop": [{"hooks": [{"type": "command", "command": "guild hook stop"}]}],
    "PreCompact": [{"matcher": "auto", "hooks": [{"type": "command", "command": "guild hook pre-compact"}]}],
    "PreToolUse": [
        {"matcher": "Bash", "hooks": [{"type": "command", "command": "guild hook pre-push"}]},
        {"matcher": "Edit|Write", "hooks": [{"type": "command", "command": "guild hook pre-edit"}]},
        {"matcher": "Bash", "hooks": [{"type": "command", "command": "guild hook pre-pr-owner"}]},
        {"matcher": "Bash", "hooks": [{"type": "command", "command": "guild hook pre-answer"}]},
    ],
}

_ASK_RULES = list(claude_settings.EXPECTED_ASK_RULES)

_ALLOW_RULES = list(claude_settings.EXPECTED_ALLOW_RULES)


class DoctorTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.home = self.root / "home"
        (self.home / ".claude").mkdir(parents=True)
        self.env = mock.patch.dict(os.environ, {"HOME": str(self.home)})
        self.env.start()
        self.addCleanup(self.env.stop)
        platform = mock.patch("guild.commands.doctor.sys.platform", "darwin")
        platform.start()
        self.addCleanup(platform.stop)

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
        self.assertIn("ok      ask rule Bash(guild party resume:*)", out)
        self.assertNotIn("missing", out)

    def test_missing_ask_rule_fails_and_names_it(self):
        self._write_full_settings(_ALL_HOOKS, ["Bash(guild raid join:*)"], _ALLOW_RULES)
        self._link_rules()
        code, out, err = self.run_cli(["doctor"], None, None)
        self.assertEqual(code, 1)
        self.assertIn("missing ask rule Bash(guild party resume:*)", out)
        self.assertIn("ok      ask rule Bash(guild raid join:*)", out)

    def test_retired_ask_rule_warns(self):
        self._write_full_settings(_ALL_HOOKS, _ASK_RULES + ["Bash(guild quest add:*)"], _ALLOW_RULES)
        self._link_rules()
        code, out, err = self.run_cli(["doctor"], None, None)
        self.assertEqual(code, 0, out + err)
        self.assertIn("warn    retired ask rule Bash(guild quest add:*) (run guild wire-settings)", out)

    def test_settings_without_permissions_reports_both_ask_rules(self):
        (self.home / ".claude" / "settings.json").write_text(json.dumps({"hooks": _ALL_HOOKS}))
        self._link_rules()
        code, out, err = self.run_cli(["doctor"], None, None)
        self.assertEqual(code, 1)
        self.assertEqual(out.count("missing ask rule"), len(claude_settings.EXPECTED_ASK_RULES))

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
        self.assertEqual(out.count("missing hook"), 10)
        self.assertEqual(out.count("missing ask rule"), len(claude_settings.EXPECTED_ASK_RULES))

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

    def test_wait_commands_match_an_expected_allow_rule(self):
        prefixes = [rule[len("Bash("):-len(":*)")] for rule in claude_settings.EXPECTED_ALLOW_RULES]
        for command in ("guild ask wait 1", "guild pr wait o/r#1"):
            self.assertTrue(any(command.startswith(prefix) for prefix in prefixes), command)

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

    def _write_current_timers(self):
        from guild.commands import timer as timer_commands

        unit_dir = self.config_home / "systemd" / "user"
        unit_dir.mkdir(parents=True)
        for unit in timer_commands.UNITS.values():
            service, timer = timer_commands.render_units(unit, "/usr/bin/guild", "10m")
            (unit_dir / unit.service_name).write_text(service)
            (unit_dir / unit.timer_name).write_text(timer)
        return unit_dir

    def _doctor_with_timer_env(self, systemctl="/usr/bin/systemctl", platform="linux"):
        def which(name):
            return {"guild": "/usr/bin/guild", "systemctl": systemctl}.get(name)

        with mock.patch("guild.commands.doctor.shutil.which", side_effect=which), mock.patch(
            "guild.commands.doctor.sys.platform", platform
        ):
            return self._doctor_out_for_clean_setup()

    def test_warns_on_missing_timers(self):
        out = self._doctor_with_timer_env()
        self.assertIn("warn    timer guild-sync-gh.timer is missing: run timers.sh", out)
        self.assertIn("warn    timer guild-compact.timer is missing: run timers.sh", out)

    def test_no_timer_warning_when_installed_units_are_current(self):
        self._write_current_timers()
        self.assertNotIn("timer guild-", self._doctor_with_timer_env())

    def test_warns_on_drifted_timer(self):
        unit_dir = self._write_current_timers()
        (unit_dir / "guild-sync-gh.service").write_text("[Service]\nExecStart=/old/guild sync\n")
        out = self._doctor_with_timer_env()
        self.assertIn("warn    timer guild-sync-gh.timer is drifted: run timers.sh", out)
        self.assertNotIn("guild-compact.timer", out)

    def test_custom_interval_is_not_drift(self):
        from guild.commands import timer as timer_commands

        unit_dir = self._write_current_timers()
        _, timer = timer_commands.render_units(timer_commands.COMPACT, "/usr/bin/guild", "3d")
        (unit_dir / "guild-compact.timer").write_text(timer)
        self.assertNotIn("timer guild-", self._doctor_with_timer_env())

    def test_no_timer_check_without_systemctl(self):
        self.assertNotIn("timer guild-", self._doctor_with_timer_env(systemctl=None))

    def test_no_timer_check_off_linux(self):
        self.assertNotIn("timer guild-", self._doctor_with_timer_env(platform="darwin"))

    def test_warns_on_project_config_with_dispatcher_key(self):
        self.register_project("acme", ["acme/app"])
        path = self.config_home / "guild" / "projects" / "acme.json"
        data = json.loads(path.read_text())
        data["dispatcher"] = {"rules": {"next_task": "on"}}
        path.write_text(json.dumps(data))
        out = self._doctor_out_for_clean_setup()
        self.assertIn("ok      project acme", out)
        self.assertIn("warn    project acme still has a 'dispatcher' key", out)

    def _write_global(self, data):
        (self.config_home / "guild").mkdir(parents=True, exist_ok=True)
        (self.config_home / "guild" / "guild.json").write_text(json.dumps(data))

    def test_missing_pre_compact_hook_fails_and_names_it(self):
        hooks = dict(_ALL_HOOKS)
        del hooks["PreCompact"]
        self._write_settings(hooks)
        self._link_rules()
        code, out, err = self.run_cli(["doctor"], None, None)
        self.assertEqual(code, 1)
        self.assertIn("missing hook PreCompact: guild hook pre-compact", out)

    def test_warns_when_threshold_is_above_the_last_compaction(self):
        self.register_project("acme", ["acme/app"])
        statusline_commands.record_compact_pct(paths.state_dir(), 31)
        statusline_commands.record_compact_pct(paths.state_dir(), 24)
        out = self._doctor_out_for_clean_setup()
        self.assertIn(
            "warn    project acme handoff_threshold 80% is above the last compaction at 24%: lower it or set handoff_margin",
            out,
        )

    def test_no_compaction_warning_when_threshold_is_below_it(self):
        self.register_project("acme", ["acme/app"])
        path = self.config_home / "guild" / "projects" / "acme.json"
        data = json.loads(path.read_text())
        data["handoff_threshold"] = 20
        path.write_text(json.dumps(data))
        statusline_commands.record_compact_pct(paths.state_dir(), 24)
        self.assertNotIn("last compaction", self._doctor_out_for_clean_setup())

    def test_no_compaction_warning_without_samples(self):
        self.register_project("acme", ["acme/app"])
        self.assertNotIn("last compaction", self._doctor_out_for_clean_setup())

    def test_margin_prints_the_derived_handoff_and_silences_the_warning(self):
        self.register_project("acme", ["acme/app"])
        self._write_global({"handoff_margin": 10})
        statusline_commands.record_compact_pct(paths.state_dir(), 85)
        out = self._doctor_out_for_clean_setup()
        self.assertIn("ok      handoff at 76% (compaction 85% − 10%)", out)
        self.assertNotIn("last compaction", out)
        self.assertNotIn("fresh session", out)

    def test_warns_when_the_derived_handoff_sits_near_a_fresh_session(self):
        self._write_global({"handoff_margin": 10})
        statusline_commands.record_compact_pct(paths.state_dir(), 21)
        statusline_commands.record_baseline_once(paths.state_dir(), "sess-1", 15)
        self.assertIn(
            "warn    handoff at 18% is under 5 points above a fresh session at 15%: sessions hand off at 20% instead",
            self._doctor_out_for_clean_setup(),
        )

    def test_margin_without_compaction_prints_no_handoff_line(self):
        self._write_global({"handoff_margin": 10})
        self.assertNotIn("handoff at", self._doctor_out_for_clean_setup())

    def test_invalid_global_config_fails(self):
        self._write_global({"handoff_margin": "ten"})
        self._write_settings(_ALL_HOOKS)
        self._link_rules()
        code, out, err = self.run_cli(["doctor"], None, None)
        self.assertEqual(code, 1)
        self.assertIn("invalid global config 'handoff_margin' must be an integer from 0 to 100", out)
