from datetime import timedelta

from guild import dispatch_launch, dispatch_rules, timeutil
from tests.dispatch_fixtures import LaunchBase


class DispatchPauseLaunchBase(LaunchBase):
    def pause(self):
        code, out, err = self.run_cli(["dispatch", "pause", "--reason", "incident"], None, None)
        self.assertEqual(code, 0, err)

    def resume(self):
        code, out, err = self.run_cli(["dispatch", "resume"], None, None)
        self.assertEqual(code, 0, err)

    def launcher(self):
        return dispatch_launch.Launcher(self.ctx(), self.tmux, self.pushes.append)


class DeferWhilePausedTests(DispatchPauseLaunchBase):
    def test_evaluate_is_busy_with_dispatch_paused(self):
        self.pause()
        verdict = self.launcher().evaluate(self.project_config(), self.trigger(12, "alpha"), "on")
        self.assertEqual((verdict.kind, verdict.reason), ("busy", "dispatch paused"))

    def test_decide_records_a_deferred_outcome(self):
        self.pause()
        line = self.decide(self.trigger(12, "alpha"), "on")
        self.assertEqual(line, "acme: ask_answered ask #12 -> deferred alpha: dispatch paused")
        row = self.decisions()[0]
        self.assertEqual((row["outcome"], row["reason"]), ("deferred", "dispatch paused"))
        self.assertEqual(self.tmux.launch_calls(), [])

    def test_preview_says_would_defer(self):
        self.pause()
        line = self.preview(self.trigger(12, "alpha"), "on")
        self.assertEqual(line, "acme: ask_answered ask #12 -> would defer alpha: dispatch paused")

    def test_resumed_pass_launches_the_deferred_trigger(self):
        self.pause()
        self.decide(self.trigger(12, "alpha"), "on")
        self.resume()
        line = self.launcher().retry_deferred(self.project_config(), self.trigger(12, "alpha"), "on")
        self.assertIn("launched alpha g2", line)
        self.assertEqual(len(self.tmux.launch_calls()), 1)


class DeferralExpiryWhilePausedTests(DispatchPauseLaunchBase):
    def _age_deferral(self):
        ctx = self.ctx()
        old = timeutil.to_iso(ctx.now - timedelta(hours=25))
        ctx.conn.execute("UPDATE dispatch_decisions SET decided_at = ?", (old,))
        ctx.conn.commit()

    def test_old_deferral_does_not_expire_while_paused(self):
        self.pause()
        self.decide(self.trigger(12, "alpha"), "on")
        self._age_deferral()
        trigger = self.trigger(12, "alpha")
        line = self.launcher().retry_deferred(self.project_config(), trigger, "on")
        self.assertIsNone(line)
        self.assertEqual(self.decisions()[0]["outcome"], "deferred")

    def test_old_deferral_expires_once_resumed(self):
        self.pause()
        self.decide(self.trigger(12, "alpha"), "on")
        self._age_deferral()
        self.resume()
        trigger = self.trigger(12, "alpha")
        line = self.launcher().retry_deferred(self.project_config(), trigger, "on")
        self.assertEqual(line, "acme: ask_answered ask #12 -> skipped alpha: deferred too long")
        self.assertEqual(self.decisions()[0]["outcome"], "skipped")


class PausedNoopTests(DispatchPauseLaunchBase):
    def setUp(self):
        super().setUp()
        self.pause()

    def test_promote_is_a_noop_while_paused(self):
        trigger = dispatch_rules.PromoteTrigger("acme", "pr_promote:acme/app#1:abc", "alpha", "acme/app", 1, True)
        launcher = self.launcher()
        self.assertIsNone(launcher.promote(self.project_config(), trigger, "on"))
        self.assertIsNone(launcher.preview_promote(trigger, "on"))
        self.assertEqual(self.decisions(), [])
        self.assertEqual(self.notices(), [])
        self.assertEqual(self.pushes, [])

    def test_announce_is_a_noop_while_paused(self):
        trigger = dispatch_rules.Trigger("acme", "merge_head", "merge_head:x", "alpha", "subject", "prompt")
        launcher = self.launcher()
        self.assertIsNone(launcher.announce(self.project_config(), trigger, "on"))
        self.assertIsNone(launcher.preview_announce(trigger, "on"))
        self.assertEqual(self.decisions(), [])
        self.assertEqual(self.notices(), [])
        self.assertEqual(self.pushes, [])

    def test_nudge_is_a_noop_while_paused(self):
        trigger = dispatch_rules.Trigger("acme", "limit_resume", "limit_resume:alpha:x", "alpha", "subject", "continue")
        launcher = self.launcher()
        self.assertIsNone(launcher.nudge(self.project_config(), trigger, "on"))
        self.assertIsNone(launcher.preview_nudge(trigger, "on"))
        self.assertEqual(self.decisions(), [])
        self.assertEqual(self.tmux.calls, [])


class WorksAfterResumeTests(DispatchPauseLaunchBase):
    def setUp(self):
        super().setUp()
        self.pause()
        self.resume()

    def test_promote_records_a_decision_after_resume(self):
        trigger = dispatch_rules.PromoteTrigger("acme", "pr_promote:acme/app#1:abc", "alpha", "acme/app", 1, True)
        line = self.launcher().promote(self.project_config(), trigger, "on")
        self.assertIsNotNone(line)
        self.assertEqual(self.decisions()[0]["outcome"], "notified")
        self.assertEqual(len(self.notices()), 1)

    def test_announce_records_a_decision_after_resume(self):
        trigger = dispatch_rules.Trigger("acme", "merge_head", "merge_head:x", "alpha", "subject", "prompt")
        line = self.launcher().announce(self.project_config(), trigger, "on")
        self.assertIsNotNone(line)
        self.assertEqual(self.decisions()[0]["outcome"], "notified")
        self.assertEqual(len(self.pushes), 1)

    def test_nudge_records_a_decision_after_resume(self):
        trigger = dispatch_rules.Trigger("acme", "limit_resume", "limit_resume:alpha:x", "alpha", "subject", "continue")
        line = self.launcher().nudge(self.project_config(), trigger, "on")
        self.assertIsNotNone(line)
        self.assertEqual(self.decisions()[0]["outcome"], "skipped")


if __name__ == "__main__":
    import unittest

    unittest.main()
