from datetime import timedelta

from guild import dispatch_launch
from guild.cli import _build_context
from guild.commands import dispatch as dispatch_commands
from tests.dispatch_fixtures import LaunchBase


class ReconcileBase(LaunchBase):
    def reconcile(self):
        ctx = self.ctx()
        launcher = dispatch_launch.Launcher(ctx, self.tmux, self.pushes.append)
        projects = {"acme": self.project_config()}
        return launcher.reconcile(projects)

    def states(self):
        return [(row["key"], row["state"], row["reason"]) for row in self.decisions()]

    def resume_party(self):
        self.run_cli(["party", "resume", "alpha"], "sess-2", self.repo_dir)


class BindConfirmationTests(ReconcileBase):
    def test_launch_that_binds_is_recorded_bound_once(self):
        self.decide(self.trigger(12, "alpha"), "on")
        self.resume_party()
        self.assertEqual(self.reconcile(), ["alpha g2 bound"])
        self.assertEqual(self.states(), [("ask_answered:12", "bound", None)])
        self.assertEqual(self.reconcile(), [])
        self.assertEqual(self.kinds().count("dispatch.bound"), 1)

    def test_launch_still_within_ten_minutes_is_left_alone(self):
        self.seed_decision("ask_answered:5", "alpha", 2, "launching", "launched", timedelta(minutes=9))
        self.tmux.windows = {"@1": "alpha"}
        self.assertEqual(self.reconcile(), [])
        self.assertEqual(self.states(), [("ask_answered:5", "launched", None)])

    def test_planned_and_skipped_rows_are_never_reconciled(self):
        self.decide(self.trigger(12, "alpha"), "dry-run")
        self.tmux.session_up = False
        self.decide(self.trigger(13, "alpha"), "on")
        self.assertEqual(self.reconcile(), [])


class FailureTests(ReconcileBase):
    def test_window_gone_before_binding_fails_once_with_notice_and_push(self):
        self.decide(self.trigger(12, "alpha"), "on")
        self.tmux.windows = {}
        lines = self.reconcile()
        self.assertEqual(lines, ["alpha g2 launch failed: window exited before binding"])
        self.assertEqual(self.states(), [("ask_answered:12", "failed", "window exited before binding")])
        self.assertEqual(len(self.notices()), 1)
        self.assertEqual(self.pushes, [["notify-send", "guild", "alpha", "dispatch-failed"]])
        self.assertEqual(self.reconcile(), [])
        self.assertEqual(len(self.notices()), 1)
        self.assertEqual(len(self.pushes), 1)

    def test_not_bound_within_ten_minutes_is_reported_and_the_window_left_running(self):
        self.seed_decision("ask_answered:5", "alpha", 2, "launching", "launched", timedelta(minutes=11))
        self.tmux.windows = {"@1": "alpha"}
        lines = self.reconcile()
        self.assertEqual(
            lines, ["alpha g2 launch failed: did not bind within 10m; window @1 left running"]
        )
        self.assertEqual(self.states()[0][1], "failed")
        self.assertNotIn("kill-pane", self.tmux.verbs())
        self.assertNotIn("kill-window", self.tmux.verbs())
        self.assertEqual(len(self.pushes), 1)
        self.assertEqual(self.reconcile(), [])

    def test_intent_without_result_is_marked_interrupted(self):
        self.seed_decision("ask_answered:5", "alpha", 2, "launching", "launching", timedelta(minutes=1))
        lines = self.reconcile()
        self.assertEqual(lines, ["alpha g2 launch failed: launch interrupted"])
        self.assertEqual(self.states(), [("ask_answered:5", "failed", "launch interrupted")])
        self.assertEqual(self.tmux.launch_calls(), [])

    def test_tmux_not_installed_counts_as_window_gone(self):
        self.decide(self.trigger(12, "alpha"), "on")
        self.tmux.installed = lambda: False
        self.assertEqual(self.reconcile(), ["alpha g2 launch failed: window exited before binding"])

    def test_rows_of_projects_without_config_are_left_alone(self):
        self.seed_decision("ask_answered:5", "alpha", 2, "launching", "launching", timedelta(minutes=1))
        ctx = self.ctx()
        launcher = dispatch_launch.Launcher(ctx, self.tmux, self.pushes.append)
        self.assertEqual(launcher.reconcile({}), [])


class BreakerIntegrationTests(ReconcileBase):
    def test_failed_party_launches_again_only_after_a_manual_resume(self):
        self.decide(self.trigger(12, "alpha"), "on")
        self.tmux.windows = {}
        self.reconcile()
        blocked = self.decide(self.trigger(13, "alpha"), "on")
        self.assertIn("skipped alpha: previous launch did not bind", blocked)
        self.resume_party()
        self.run_cli(["handoff", "--in-flight", "x", "--learned", "y"], "sess-2", self.repo_dir)
        self.assertIn("launched alpha g3", self.decide(self.trigger(14, "alpha"), "on"))


class PassIntegrationTests(ReconcileBase):
    def run_pass(self, dry_run):
        ctx = _build_context(None, self.repo_dir)
        try:
            return dispatch_commands.run(ctx, dry_run, self.tmux, self.pushes.append)
        finally:
            ctx.conn.close()

    def test_pass_reports_reconcile_lines_and_dry_run_skips_them(self):
        self.decide(self.trigger(12, "alpha"), "on")
        self.resume_party()
        seq = self.max_seq()
        self.assertEqual(self.run_pass(True), ["acme: would initialize cursor at seq {}".format(seq)])
        self.assertEqual(self.states()[0][1], "launched")
        lines = self.run_pass(False)
        self.assertEqual(lines, ["acme: cursor initialized at seq {}".format(seq), "alpha g2 bound"])
        self.assertEqual(self.states()[0][1], "bound")

    def max_seq(self):
        return self.ctx().conn.execute("SELECT MAX(seq) AS seq FROM events").fetchone()["seq"]
