import os
from datetime import timedelta

from guild import dispatch_launch, timeutil
from tests.dispatch_fixtures import LaunchBase
from tests.fake_tmux import FakeTmux

_SUGGESTION = "alpha ready to resume (ask_answered ask #12): run guild revive --party alpha"


class SuggestionTests(LaunchBase):
    def test_an_on_rule_suggests_the_revive_and_never_touches_tmux(self):
        line = self.decide(self.trigger(12, "alpha"), "on")
        self.assertEqual(line, "acme: ask_answered ask #12 -> suggested revive alpha g2")
        self.assertEqual(self.tmux.launch_calls(), [])
        self.assertEqual(self.tmux.verbs(), ["list-windows"])
        self.assertFalse([call for call in self.tmux.calls if call[0] == "send-keys"])

    def test_decision_notice_and_push_are_recorded(self):
        self.decide(self.trigger(12, "alpha"), "on")
        row = self.decisions()[0]
        self.assertEqual((row["outcome"], row["state"], row["party"], row["generation"]), ("suggested", None, "alpha", 2))
        self.assertEqual(self.kinds(), ["dispatch.decided"])
        notice = self.notices()[0]
        self.assertEqual((notice["scope"], notice["text"]), ("project:acme", _SUGGESTION))
        self.assertEqual(self.pushes, [["notify-send", "guild", "alpha", "ready"]])

    def test_second_pass_posts_nothing_new(self):
        self.assertIsNotNone(self.decide(self.trigger(12, "alpha"), "on"))
        self.assertIsNone(self.decide(self.trigger(12, "alpha"), "on"))
        self.assertEqual(self.kinds().count("dispatch.decided"), 1)
        self.assertEqual(len(self.notices()), 1)
        self.assertEqual(len(self.pushes), 1)

    def test_missing_notify_command_is_tolerated(self):
        def missing(argv):
            raise FileNotFoundError(argv[0])

        launcher = dispatch_launch.Launcher(self.ctx(), self.tmux, missing)
        line = launcher.decide(self.project_config(), self.trigger(12, "alpha"), "on")
        self.assertIn("suggested revive alpha g2", line)

    def test_dry_run_rule_records_planned_without_notice_or_push(self):
        line = self.decide(self.trigger(12, "alpha"), "dry-run")
        self.assertEqual(line, "acme: ask_answered ask #12 -> planned: suggest revive alpha g2 (dry-run)")
        self.assertEqual(self.notices(), [])
        self.assertEqual(self.pushes, [])
        row = self.decisions()[0]
        self.assertEqual((row["mode"], row["outcome"]), ("dry-run", "planned"))

    def test_dry_run_decision_does_not_block_the_real_one(self):
        self.decide(self.trigger(12, "alpha"), "dry-run")
        self.assertIn("suggested revive alpha g2", self.decide(self.trigger(12, "alpha"), "on"))
        self.assertEqual([row["mode"] for row in self.decisions()], ["dry-run", "on"])

    def test_real_decision_blocks_a_later_dry_run_decision(self):
        self.decide(self.trigger(12, "alpha"), "on")
        self.assertIsNone(self.decide(self.trigger(12, "alpha"), "dry-run"))

    def test_preview_says_would_suggest_and_writes_nothing(self):
        before = self.ctx().conn.execute("SELECT COUNT(*) AS n FROM events").fetchone()["n"]
        line = self.preview(self.trigger(12, "alpha"), "on")
        self.assertEqual(line, "acme: ask_answered ask #12 -> would suggest revive alpha g2")
        self.assertEqual(self.preview(self.trigger(12, "alpha"), "dry-run"), line)
        after = self.ctx().conn.execute("SELECT COUNT(*) AS n FROM events").fetchone()["n"]
        self.assertEqual(before, after)

    def test_preview_of_a_duplicate_is_silent(self):
        self.decide(self.trigger(12, "alpha"), "on")
        self.assertIsNone(self.preview(self.trigger(12, "alpha"), "on"))


class BusyTests(LaunchBase):
    def assert_deferred(self, reason):
        line = self.decide(self.trigger(12, "alpha"), "on")
        self.assertEqual(line, "acme: ask_answered ask #12 -> deferred alpha: {}".format(reason))
        self.assertEqual(self.notices(), [])
        self.assertEqual(self.pushes, [])
        row = self.decisions()[0]
        self.assertEqual((row["outcome"], row["reason"]), ("deferred", reason))

    def test_live_leader_session_is_deferred(self):
        self.write_session(os.getpid(), "sess-1", "alpha")
        self.assert_deferred("live session")

    def test_open_window_named_after_party_is_deferred(self):
        self.tmux.windows = {"@3": "alpha"}
        self.assert_deferred("open window")

    def test_paused_member_raid_is_deferred(self):
        now = self.ctx().now
        expires = timeutil.to_iso(now + timedelta(hours=8))
        self.record("raid.joined", "alpha", {"raid": "ci", "party": "alpha", "expires_at": expires, "lead": True}, now)
        self.record("raid.paused", "alpha", {"raid": "ci", "party": "alpha"}, now)
        self.assert_deferred("raid ci paused")

    def test_busy_reason_is_shown_in_preview(self):
        self.tmux.windows = {"@3": "alpha"}
        line = self.preview(self.trigger(12, "alpha"), "on")
        self.assertEqual(line, "acme: ask_answered ask #12 -> would defer alpha: open window")
        self.assertEqual(self.kinds(), [])

    def test_deferral_does_not_consume_the_key(self):
        self.tmux.windows = {"@3": "alpha"}
        self.decide(self.trigger(12, "alpha"), "on")
        self.tmux.windows = {}
        self.assertIn("suggested revive alpha g2", self.decide(self.trigger(12, "alpha"), "on"))
        self.assertEqual(self.decisions()[0]["outcome"], "suggested")

    def test_still_busy_again_records_nothing_new(self):
        self.tmux.windows = {"@3": "alpha"}
        self.decide(self.trigger(12, "alpha"), "on")
        before = self.decisions()
        self.assertIsNone(self.decide(self.trigger(12, "alpha"), "on"))
        self.assertEqual(self.decisions(), before)
        self.assertEqual(self.kinds(), ["dispatch.decided"])

    def test_deferred_party_that_closed_is_skipped(self):
        self.tmux.windows = {"@3": "alpha"}
        self.decide(self.trigger(12, "alpha"), "on")
        self.run_cli(["party", "close", "alpha", "--force"], None, self.repo_dir)
        line = self.decide(self.trigger(12, "alpha"), "on")
        self.assertIn("skipped alpha: party closed", line)
        self.assertEqual(self.decisions()[0]["outcome"], "skipped")

    def test_dry_run_rule_defers_too(self):
        self.tmux.windows = {"@3": "alpha"}
        line = self.decide(self.trigger(12, "alpha"), "dry-run")
        self.assertIn("deferred alpha: open window", line)
        self.assertEqual(self.decisions()[0]["mode"], "dry-run")

    def test_tmux_not_installed_still_suggests(self):
        self.tmux = FakeTmux(False, False, {}, 0)
        line = self.decide(self.trigger(12, "alpha"), "on")
        self.assertIn("suggested revive alpha g2", line)
        self.assertEqual(self.tmux.calls, [])


class SkipTests(LaunchBase):
    def test_party_that_did_not_hand_off_is_skipped_with_notice(self):
        self.run_cli(["party", "resume", "alpha"], "sess-2", self.repo_dir)
        line = self.decide(self.trigger(12, "alpha"), "on")
        self.assertIn("skipped alpha: party not handed off", line)
        notice = self.notices()[0]
        self.assertEqual(notice["scope"], "project:acme")
        self.assertIn("guild revive --party alpha", notice["text"])
        self.assertEqual(self.pushes, [])

    def test_keeper_is_skipped_without_notice(self):
        self.run_cli(["party", "start", "kay", "--keeper"], "sess-3", self.repo_dir)
        self.run_cli(["handoff", "--in-flight", "x", "--learned", "y"], "sess-3", self.repo_dir)
        line = self.decide(self.trigger(12, "kay"), "on")
        self.assertIn("skipped kay: keeper", line)
        self.assertEqual(self.notices(), [])

    def test_closed_party_is_skipped_without_notice(self):
        self.run_cli(["party", "close", "alpha", "--force"], None, self.repo_dir)
        line = self.decide(self.trigger(12, "alpha"), "on")
        self.assertIn("skipped alpha: party closed", line)
        self.assertEqual(self.notices(), [])

    def test_missing_party_is_skipped_without_notice(self):
        line = self.decide(self.trigger(12, "ghost"), "on")
        self.assertIn("skipped ghost: party closed", line)
        self.assertEqual(self.notices(), [])


class ErrorIsolationTests(LaunchBase):
    def test_unexpected_error_while_deciding_records_an_error_decision(self):
        launcher = dispatch_launch.Launcher(self.ctx(), self.tmux, self.pushes.append)
        self.tmux.installed = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
        line = launcher.decide(self.project_config(), self.trigger(12, "alpha"), "on")
        self.assertIn("-> error alpha: RuntimeError", line)
        row = self.decisions()[0]
        self.assertEqual((row["outcome"], row["reason"]), ("skipped", "error: RuntimeError"))
