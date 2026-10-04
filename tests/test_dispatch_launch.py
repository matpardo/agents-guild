import os
import shlex
from datetime import timedelta

from guild import dispatch_launch, timeutil
from tests.dispatch_fixtures import PROMPT, LaunchBase
from tests.fake_tmux import FakeTmux


class HappyPathTests(LaunchBase):
    def test_launches_the_next_generation_in_the_guild_session(self):
        line = self.decide(self.trigger(12, "alpha"), "on")
        self.assertEqual(
            line, "acme: ask_answered ask #12 -> launched alpha g2 (window @10, mode acceptEdits)"
        )
        launch = self.tmux.launch_calls()[0]
        self.assertEqual(launch[:7], ["new-window", "-t", "guild:", "-n", "alpha", "-c", str(self.repo_dir.resolve())])
        command = launch[-1]
        self.assertTrue(command.startswith("GUILD_RESUME=alpha claude -n alpha-g2 --permission-mode acceptEdits "))
        self.assertTrue(command.endswith(shlex.quote(PROMPT)))
        self.assertNotIn("--remote-control", command)

    def test_event_order_is_intent_then_window_then_launched(self):
        self.decide(self.trigger(12, "alpha"), "on")
        self.assertEqual(self.kinds()[-3:], ["dispatch.decided", "leader.window_launched", "dispatch.launched"])
        row = self.decisions()[0]
        self.assertEqual((row["outcome"], row["state"], row["window_id"]), ("launching", "launched", "@10"))
        self.assertEqual((row["party"], row["generation"], row["permission_mode"]), ("alpha", 2, "acceptEdits"))
        window = self.ctx().conn.execute("SELECT * FROM leader_windows WHERE party = 'alpha'").fetchone()
        self.assertEqual((window["generation"], window["window_id"]), (2, "@10"))

    def test_window_is_pinned_and_session_titles_are_left_alone(self):
        self.decide(self.trigger(12, "alpha"), "on")
        self.assertIn(["set-option", "-w", "-t", "@10", "automatic-rename", "off"], self.tmux.calls)
        self.assertNotIn(["set-option", "-t", "guild", "set-titles", "on"], self.tmux.calls)
        self.assertFalse([call for call in self.tmux.calls if "set-titles" in call])

    def test_window_is_created_detached_so_focus_never_moves(self):
        self.decide(self.trigger(12, "alpha"), "on")
        launch = self.tmux.launch_calls()[0]
        self.assertEqual(launch[0], "new-window")
        self.assertIn("-d", launch[:-1])

    def test_intent_is_committed_before_tmux_is_invoked(self):
        seen = []
        original = self.tmux.run

        def spy(args):
            if args[0] == "new-window":
                seen.append(self.kinds())
            return original(args)

        self.tmux.run = spy
        self.decide(self.trigger(12, "alpha"), "on")
        self.assertEqual(seen, [["dispatch.decided"]])

    def test_never_creates_the_tmux_session(self):
        self.tmux.session_up = False
        line = self.decide(self.trigger(12, "alpha"), "on")
        self.assertIn("skipped alpha: tmux session guild not running", line)
        self.assertNotIn("new-session", self.tmux.verbs())
        self.assertEqual(self.tmux.launch_calls(), [])


class DedupeTests(LaunchBase):
    def test_a_key_is_decided_once(self):
        self.assertIsNotNone(self.decide(self.trigger(12, "alpha"), "on"))
        self.assertIsNone(self.decide(self.trigger(12, "alpha"), "on"))
        self.assertEqual(self.kinds().count("dispatch.decided"), 1)
        self.assertEqual(len(self.tmux.launch_calls()), 1)

    def test_dry_run_decision_does_not_block_the_real_one(self):
        self.assertIn("planned: launch alpha g2", self.decide(self.trigger(12, "alpha"), "dry-run"))
        self.assertIn("launched alpha g2", self.decide(self.trigger(12, "alpha"), "on"))
        self.assertEqual([row["mode"] for row in self.decisions()], ["dry-run", "on"])

    def test_real_decision_blocks_a_later_dry_run_decision(self):
        self.decide(self.trigger(12, "alpha"), "on")
        self.assertIsNone(self.decide(self.trigger(12, "alpha"), "dry-run"))

    def test_skipped_key_is_not_decided_again(self):
        self.tmux.session_up = False
        self.decide(self.trigger(12, "alpha"), "on")
        self.tmux.session_up = True
        self.assertIsNone(self.decide(self.trigger(12, "alpha"), "on"))
        self.assertEqual(self.tmux.launch_calls(), [])

    def test_two_triggers_for_one_party_launch_once(self):
        self.assertIn("launched", self.decide(self.trigger(12, "alpha"), "on"))
        self.assertIsNone(self.decide(self.trigger(13, "alpha"), "on"))
        self.assertEqual(len(self.tmux.launch_calls()), 1)


class BusyTests(LaunchBase):
    def assert_silent(self):
        self.assertIsNone(self.decide(self.trigger(12, "alpha"), "on"))
        self.assertEqual(self.kinds(), [])
        self.assertEqual(self.tmux.launch_calls(), [])
        self.assertEqual(self.notices(), [])

    def test_live_leader_session_is_silent(self):
        self.write_session(os.getpid(), "sess-1", "alpha")
        self.assert_silent()

    def test_open_window_named_after_party_is_silent(self):
        self.tmux.windows = {"@3": "alpha"}
        self.assert_silent()

    def test_launch_in_flight_is_silent(self):
        self.seed_decision("ask_answered:5", "alpha", 2, "launching", "launched", timedelta(minutes=2))
        self.assert_silent_after_seed()

    def assert_silent_after_seed(self):
        before = self.kinds()
        self.assertIsNone(self.decide(self.trigger(12, "alpha"), "on"))
        self.assertEqual(self.kinds(), before)
        self.assertEqual(self.tmux.launch_calls(), [])

    def test_paused_member_raid_is_silent(self):
        now = self.ctx().now
        expires = timeutil.to_iso(now + timedelta(hours=8))
        self.record("raid.joined", "alpha", {"raid": "ci", "party": "alpha", "expires_at": expires, "lead": True}, now)
        self.record("raid.paused", "alpha", {"raid": "ci", "party": "alpha"}, now)
        self.assert_silent_after_seed()

    def test_busy_reason_is_shown_in_preview(self):
        self.tmux.windows = {"@3": "alpha"}
        line = self.preview(self.trigger(12, "alpha"), "on")
        self.assertEqual(line, "acme: ask_answered ask #12 -> would skip alpha: open window")

    def test_busy_does_not_consume_the_key(self):
        self.tmux.windows = {"@3": "alpha"}
        self.assertIsNone(self.decide(self.trigger(12, "alpha"), "on"))
        self.tmux.windows = {}
        self.assertIn("launched alpha g2", self.decide(self.trigger(12, "alpha"), "on"))


class SkipTests(LaunchBase):
    def assert_skipped(self, line, reason):
        self.assertIn("skipped alpha: {}".format(reason), line)
        self.assertEqual(self.tmux.launch_calls(), [])
        row = self.decisions()[0]
        self.assertEqual((row["outcome"], row["state"]), ("skipped", None))
        self.assertTrue(row["reason"].startswith(reason))
        self.assertEqual(self.kinds(), ["dispatch.decided"])

    def test_party_that_did_not_hand_off_is_skipped_with_notice(self):
        self.run_cli(["party", "resume", "alpha"], "sess-2", self.repo_dir)
        line = self.decide(self.trigger(12, "alpha"), "on")
        self.assert_skipped(line, "party not handed off")
        notice = self.notices()[0]
        self.assertEqual(notice["scope"], "project:acme")
        self.assertIn("guild revive --party alpha", notice["text"])

    def test_keeper_is_skipped_without_notice(self):
        self.run_cli(["party", "start", "kay", "--keeper"], "sess-3", self.repo_dir)
        self.run_cli(["handoff", "--in-flight", "x", "--learned", "y"], "sess-3", self.repo_dir)
        line = self.decide(self.trigger(12, "kay"), "on")
        self.assertIn("skipped kay: keeper", line)
        self.assertEqual(self.notices(), [])
        self.assertEqual(self.tmux.launch_calls(), [])

    def test_closed_party_is_skipped_without_notice(self):
        self.run_cli(["party", "close", "alpha", "--force"], None, self.repo_dir)
        line = self.decide(self.trigger(12, "alpha"), "on")
        self.assert_skipped(line, "party closed")
        self.assertEqual(self.notices(), [])

    def test_missing_party_is_skipped_without_notice(self):
        line = self.decide(self.trigger(12, "ghost"), "on")
        self.assertIn("skipped ghost: party closed", line)
        self.assertEqual(self.notices(), [])

    def test_missing_cwd_is_skipped_with_notice(self):
        self.locate("alpha", 1, self.root / "gone", None)
        line = self.decide(self.trigger(12, "alpha"), "on")
        self.assert_skipped(line, "cwd missing")
        self.assertEqual(len(self.notices()), 1)

    def test_cwd_outside_the_project_is_skipped_with_notice(self):
        self.locate("alpha", 1, self.other_dir, None)
        line = self.decide(self.trigger(12, "alpha"), "on")
        self.assert_skipped(line, "cwd outside project")
        self.assertEqual(len(self.notices()), 1)

    def test_cwd_with_a_hash_is_skipped_as_unsafe_with_notice(self):
        unsafe = self.repo_dir / "a#b"
        unsafe.mkdir()
        self.locate("alpha", 1, unsafe, None)
        line = self.decide(self.trigger(12, "alpha"), "on")
        self.assert_skipped(line, "cwd unsafe")
        self.assertEqual(len(self.notices()), 1)

    def test_unknown_cwd_is_skipped_with_notice(self):
        self.ctx().conn.execute("UPDATE leaders SET cwd = NULL WHERE party = 'alpha'")
        line = self.decide(self.trigger(12, "alpha"), "on")
        self.assert_skipped(line, "cwd unknown")
        self.assertEqual(len(self.notices()), 1)

    def test_tmux_not_installed_is_skipped_with_notice(self):
        self.tmux = FakeTmux(False, True, {}, 0)
        line = self.decide(self.trigger(12, "alpha"), "on")
        self.assert_skipped(line, "tmux session guild not running")
        self.assertEqual(self.tmux.calls, [])
        self.assertEqual(len(self.notices()), 1)

    def test_missing_guild_session_posts_one_notice_per_hour(self):
        self.tmux.session_up = False
        self.decide(self.trigger(12, "alpha"), "on")
        self.decide(self.trigger(13, "alpha"), "on")
        self.assertEqual(len(self.notices()), 1)
        self.assertEqual(len(self.decisions()), 2)
        self.assertIn("tmux new -s guild", self.notices()[0]["text"])

    def test_rate_limit_skips_with_one_notice_and_counts_only_real_launches(self):
        for number in range(3):
            self.seed_decision("ask_answered:{}".format(number), "gamma", 2, "launching", "bound", timedelta(minutes=10))
        self.seed_decision("ask_answered:90", "delta", 2, "planned", None, timedelta(minutes=10))
        self.seed_decision("ask_answered:91", "gamma", 2, "launching", "bound", timedelta(hours=2))
        line = self.decide(self.trigger(12, "alpha"), "on")
        self.assertIn("skipped alpha: rate limit (3/3)", line)
        self.decide(self.trigger(13, "alpha"), "on")
        self.assertEqual(len(self.notices()), 1)
        self.assertEqual(self.tmux.launch_calls(), [])

    def test_planned_rows_do_not_count_toward_the_limit(self):
        for number in range(5):
            self.seed_decision("ask_answered:{}".format(number), "gamma", 2, "planned", None, timedelta(minutes=10))
        self.assertIn("launched alpha g2", self.decide(self.trigger(12, "alpha"), "on"))

    def test_notice_text_carries_only_names_and_ids(self):
        self.locate("alpha", 1, self.root / "gone", None)
        self.decide(self.trigger(12, "alpha"), "on")
        self.assertNotIn(str(self.root), self.notices()[0]["text"])
        self.assertIn("alpha", self.notices()[0]["text"])


class BreakerTests(LaunchBase):
    def test_failed_launch_blocks_the_party_until_the_generation_advances(self):
        self.seed_decision("ask_answered:5", "alpha", 2, "launching", "failed", timedelta(minutes=20))
        line = self.decide(self.trigger(12, "alpha"), "on")
        self.assertIn("skipped alpha: previous launch did not bind", line)
        self.assertEqual(self.notices(), [])
        self.assertEqual(self.tmux.launch_calls(), [])

    def test_manual_resume_clears_the_breaker(self):
        self.seed_decision("ask_answered:5", "alpha", 2, "launching", "failed", timedelta(minutes=20))
        self.run_cli(["party", "resume", "alpha"], "sess-2", self.repo_dir)
        self.run_cli(["handoff", "--in-flight", "x", "--learned", "y"], "sess-2", self.repo_dir)
        line = self.decide(self.trigger(12, "alpha"), "on")
        self.assertIn("launched alpha g3", line)


class ModeTests(LaunchBase):
    def launched_mode(self, index, configured, party_mode):
        party = "mode{}".format(index)
        session = "sess-m{}".format(index)
        self.write_block(configured, 20)
        self.run_cli(["party", "start", party], session, self.repo_dir)
        self.run_cli(["handoff", "--in-flight", "x", "--learned", "y"], session, self.repo_dir)
        self.locate(party, 1, self.repo_dir.resolve(), party_mode)
        self.decide(self.trigger(100 + index, party), "on")
        row = [row for row in self.decisions() if row["party"] == party][0]
        return row["permission_mode"], self.tmux.launch_calls()[-1][-1]

    def test_effective_mode_table(self):
        cases = [
            ("acceptEdits", None, "acceptEdits"),
            ("acceptEdits", "manual", "manual"),
            ("acceptEdits", "plan", "plan"),
            ("acceptEdits", "bypassPermissions", "acceptEdits"),
            ("acceptEdits", "dontAsk", "acceptEdits"),
            ("acceptEdits", "unheardOf", "acceptEdits"),
            ("auto", "acceptEdits", "auto"),
            ("auto", "manual", "manual"),
            ("manual", "acceptEdits", "manual"),
            ("manual", "auto", "manual"),
            ("manual", "plan", "plan"),
            ("manual", None, "manual"),
        ]
        for index, (configured, party_mode, expected) in enumerate(cases):
            with self.subTest(configured=configured, party_mode=party_mode):
                mode, command = self.launched_mode(index, configured, party_mode)
                self.assertEqual(mode, expected)
                self.assertIn("--permission-mode {} ".format(expected), command)


class FailureTests(LaunchBase):
    def test_window_creation_failure_records_failure_notice_and_push(self):
        self.tmux.create_returncode = 1
        line = self.decide(self.trigger(12, "alpha"), "on")
        self.assertEqual(
            line, "acme: ask_answered ask #12 -> launch failed alpha g2: tmux could not create the window"
        )
        self.assertEqual(self.kinds(), ["dispatch.decided", "dispatch.launch_failed"])
        row = self.decisions()[0]
        self.assertEqual((row["state"], row["reason"]), ("failed", "tmux could not create the window"))
        self.assertEqual(len(self.notices()), 1)
        self.assertEqual(self.pushes, [["notify-send", "guild", "alpha", "dispatch-failed"]])

    def test_exception_records_failure_with_the_exception_type(self):
        self.tmux.raise_on_create = RuntimeError("boom")
        line = self.decide(self.trigger(12, "alpha"), "on")
        self.assertIn("launch failed alpha g2: RuntimeError", line)
        row = self.decisions()[0]
        self.assertEqual((row["state"], row["reason"]), ("failed", "RuntimeError"))
        self.assertNotIn("boom", self.notices()[0]["text"])

    def test_missing_notify_command_is_tolerated(self):
        self.notify = {"command": ["definitely-missing"]}
        self.write_block("acceptEdits", 3)
        self.tmux.create_returncode = 1

        def missing(argv):
            raise FileNotFoundError(argv[0])

        ctx = self.ctx()
        launcher = dispatch_launch.Launcher(ctx, self.tmux, missing)
        line = launcher.decide(self.project_config(), self.trigger(12, "alpha"), "on")
        self.assertIn("launch failed", line)


class DryRunRuleTests(LaunchBase):
    def test_dry_run_rule_records_planned_without_touching_tmux_or_notices(self):
        line = self.decide(self.trigger(12, "alpha"), "dry-run")
        self.assertEqual(
            line, "acme: ask_answered ask #12 -> planned: launch alpha g2 (dry-run, mode acceptEdits)"
        )
        self.assertEqual(self.tmux.launch_calls(), [])
        self.assertEqual(self.notices(), [])
        row = self.decisions()[0]
        self.assertEqual((row["mode"], row["outcome"], row["state"]), ("dry-run", "planned", None))
        self.assertEqual((row["generation"], row["permission_mode"]), (2, "acceptEdits"))
        self.assertEqual(self.kinds(), ["dispatch.decided"])

    def test_preview_of_a_launch_writes_nothing(self):
        before = self.ctx().conn.execute("SELECT COUNT(*) AS n FROM events").fetchone()["n"]
        line = self.preview(self.trigger(12, "alpha"), "on")
        self.assertEqual(
            line, "acme: ask_answered ask #12 -> would launch alpha g2 (mode acceptEdits)"
        )
        after = self.ctx().conn.execute("SELECT COUNT(*) AS n FROM events").fetchone()["n"]
        self.assertEqual(before, after)
        self.assertEqual(self.tmux.launch_calls(), [])

    def test_preview_of_a_dry_run_rule(self):
        line = self.preview(self.trigger(12, "alpha"), "dry-run")
        self.assertEqual(
            line, "acme: ask_answered ask #12 -> would plan launch alpha g2 (mode acceptEdits)"
        )

    def test_preview_of_a_skip_posts_no_notice(self):
        self.tmux.session_up = False
        line = self.preview(self.trigger(12, "alpha"), "on")
        self.assertEqual(
            line, "acme: ask_answered ask #12 -> would skip alpha: tmux session guild not running"
        )
        self.assertEqual(self.notices(), [])
        self.assertEqual(self.kinds(), [])

    def test_preview_of_a_duplicate_is_silent(self):
        self.decide(self.trigger(12, "alpha"), "on")
        self.assertIsNone(self.preview(self.trigger(12, "alpha"), "on"))


class ErrorIsolationTests(LaunchBase):
    def test_unexpected_error_while_deciding_records_an_error_decision(self):
        ctx = self.ctx()
        launcher = dispatch_launch.Launcher(ctx, self.tmux, self.pushes.append)
        self.tmux.installed = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
        line = launcher.decide(self.project_config(), self.trigger(12, "alpha"), "on")
        self.assertIn("-> error alpha: RuntimeError", line)
        row = self.decisions()[0]
        self.assertEqual((row["outcome"], row["reason"]), ("skipped", "error: RuntimeError"))
