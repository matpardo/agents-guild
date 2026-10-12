import json
import os

from guild import dispatch_launch
from guild.cli import _build_context
from guild.commands import dispatch as dispatch_commands
from tests.dispatch_fixtures import LaunchBase


class AbandonedBase(LaunchBase):
    def resume_party(self):
        self.run_cli(["party", "resume", "alpha"], "sess-2", self.repo_dir)

    def launcher(self):
        return dispatch_launch.Launcher(self.ctx(), self.tmux, self.pushes.append)

    def handoff_abandoned(self):
        return self.launcher().handoff_abandoned_parties({"acme": self.project_config()})

    def preview_handoff_abandoned(self):
        return self.launcher().preview_handoff_abandoned_parties({"acme": self.project_config()})

    def party_row(self):
        return self.ctx().conn.execute("SELECT * FROM parties WHERE name = 'alpha'").fetchone()

    def auto_handed_off_events(self):
        rows = self.ctx().conn.execute("SELECT payload FROM events WHERE kind = 'party.handed_off'").fetchall()
        return [row for row in rows if json.loads(row["payload"])["auto"]]

    def make_abandoned_party(self):
        self.decide(self.trigger(12, "alpha"), "on")
        self.resume_party()
        self.tmux.windows = {}


class AbandonedPartyTests(AbandonedBase):
    def test_dead_leader_and_gone_window_gets_automatic_handoff(self):
        self.make_abandoned_party()
        lines = self.handoff_abandoned()
        self.assertEqual(lines, ["alpha g2: automatic handoff written (leader and window gone)"])
        self.assertEqual(self.party_row()["state"], "awaiting-leader")
        self.assertEqual(len(self.auto_handed_off_events()), 1)

    def test_live_leader_is_left_alone(self):
        self.make_abandoned_party()
        self.write_session(os.getpid(), "sess-2", "alpha")
        self.assertEqual(self.handoff_abandoned(), [])
        self.assertEqual(self.party_row()["state"], "active")
        self.assertEqual(self.auto_handed_off_events(), [])

    def test_window_still_open_is_left_alone(self):
        self.decide(self.trigger(12, "alpha"), "on")
        self.resume_party()
        self.tmux.windows = {"@10": "alpha"}
        self.assertEqual(self.handoff_abandoned(), [])
        self.assertEqual(self.party_row()["state"], "active")
        self.assertEqual(self.auto_handed_off_events(), [])

    def test_party_never_guild_launched_this_generation_is_left_alone(self):
        self.resume_party()
        self.tmux.windows = {}
        self.assertEqual(self.handoff_abandoned(), [])
        self.assertEqual(self.party_row()["state"], "active")
        self.assertEqual(self.auto_handed_off_events(), [])

    def test_keeper_party_is_left_alone(self):
        self.make_abandoned_party()
        self.ctx().conn.execute("UPDATE parties SET keeper = 1 WHERE name = 'alpha'")
        self.assertEqual(self.handoff_abandoned(), [])
        self.assertEqual(self.auto_handed_off_events(), [])

    def test_closed_party_is_left_alone(self):
        self.make_abandoned_party()
        self.run_cli(["party", "close", "alpha", "--force"], None, self.repo_dir)
        self.assertEqual(self.handoff_abandoned(), [])
        self.assertEqual(len(self.auto_handed_off_events()), 0)

    def test_tmux_not_installed_is_left_alone(self):
        self.make_abandoned_party()
        self.tmux.installed = lambda: False
        self.assertEqual(self.handoff_abandoned(), [])
        self.assertEqual(self.party_row()["state"], "active")
        self.assertEqual(self.auto_handed_off_events(), [])

    def test_preview_describes_without_writing(self):
        self.make_abandoned_party()
        lines = self.preview_handoff_abandoned()
        self.assertEqual(lines, ["alpha g2: would write an automatic handoff (leader and window gone)"])
        self.assertEqual(self.party_row()["state"], "active")
        self.assertEqual(self.auto_handed_off_events(), [])

    def test_project_without_dispatcher_block_is_excluded(self):
        self.make_abandoned_party()
        self.assertEqual(self.launcher().handoff_abandoned_parties({}), [])
        self.assertEqual(self.auto_handed_off_events(), [])


class PassIntegrationTests(AbandonedBase):
    def run_pass(self, dry_run):
        ctx = _build_context(None, self.repo_dir)
        try:
            return dispatch_commands.run(ctx, dry_run, self.tmux, self.pushes.append)
        finally:
            ctx.conn.close()

    def test_real_pass_surfaces_the_automatic_handoff_line(self):
        self.make_abandoned_party()
        lines = self.run_pass(False)
        self.assertIn("alpha g2: automatic handoff written (leader and window gone)", lines)

    def test_dry_run_pass_surfaces_the_preview_line_without_writing(self):
        self.make_abandoned_party()
        lines = self.run_pass(True)
        self.assertIn("alpha g2: would write an automatic handoff (leader and window gone)", lines)
        self.assertEqual(self.party_row()["state"], "active")
