import json

from guild.cli import _build_context
from guild.commands import dispatch as dispatch_commands
from tests.fake_tmux import FakeTmux
from tests.mq_fixtures import OPEN_VIEW, MergeQueueTestCase


class MergeHeadTests(MergeQueueTestCase):
    def setUp(self):
        super().setUp()
        self.write_block({"merge_head": "on"})
        for name, session in (("alpha", "sess-1"), ("beta", "sess-2")):
            self.start_party(name, session)
            self.run_cli(["quest", "add", "q" + name, "--title", name, "--no-epic"], session, self.repo_dir)
            self.run_cli(["task", "add", "q{}/T01".format(name), "--title", "t"], session, self.repo_dir)
        self.track("sess-1", 1, "qalpha/T01", "ready")
        self.track("sess-2", 2, "qbeta/T01", "ready")
        self.pushes = []
        self.run_pass()

    def write_block(self, rules):
        path = self.config_home / "guild" / "projects" / "acme.json"
        data = json.loads(path.read_text())
        data["dispatcher"] = {"rules": rules}
        data["notify"] = {"command": ["notify-send", "guild"]}
        path.write_text(json.dumps(data))

    def run_pass(self, dry_run=False):
        ctx = _build_context(None, self.repo_dir)
        try:
            return dispatch_commands.run(ctx, dry_run, FakeTmux(True, True, {}, 0), self.pushes.append)
        finally:
            ctx.conn.close()

    def notices(self):
        code, out, err = self.run_cli(["notices"], "sess-1", self.repo_dir)
        return [line for line in out.splitlines() if "first in the merge queue" in line]

    def merge_first_and_track_next(self):
        self.write_gh_fixture("view_acme-app_1", dict(OPEN_VIEW, state="MERGED", mergedAt="2026-10-04T00:00:00Z"))
        code, out, err = self.sync_gh("sess-1")
        self.assertEqual(code, 0, err)
        self.track("sess-1", 3, "qalpha/T01", "ready")

    def test_each_solo_party_head_is_announced_once(self):
        self.assertEqual(len(self.notices()), 2)
        self.assertTrue(
            any("alpha: acme/app#1 is first in the merge queue; run guild pr ready-check acme/app#1" in line for line in self.notices())
        )
        self.assertEqual(self.run_pass(), ["nothing to dispatch"])
        self.assertEqual(len(self.notices()), 2)

    def test_notify_command_runs_for_the_owning_party(self):
        self.assertEqual(self.pushes, [["notify-send", "guild", "alpha", "merge-head"], ["notify-send", "guild", "beta", "merge-head"]])

    def test_new_head_notifies_its_owner(self):
        self.merge_first_and_track_next()
        lines = self.run_pass()
        self.assertEqual(lines, ["acme: merge_head acme/app#3 -> notified alpha"])
        self.assertEqual(len(self.notices()), 3)

    def test_dry_run_flag_prints_plan_and_records_nothing(self):
        self.merge_first_and_track_next()
        before = len(self.pushes)
        self.assertEqual(self.run_pass(True), ["acme: merge_head acme/app#3 -> would notify alpha"])
        self.assertEqual(len(self.pushes), before)
        self.assertEqual(len(self.notices()), 2)

    def test_dry_run_mode_records_a_plan_without_notifying(self):
        self.write_block({"merge_head": "dry-run"})
        self.merge_first_and_track_next()
        self.assertEqual(self.run_pass(), ["acme: merge_head acme/app#3 -> planned: notify alpha"])
        self.assertEqual(len(self.notices()), 2)

    def test_rule_absent_does_nothing(self):
        self.write_block({})
        self.merge_first_and_track_next()
        self.assertEqual(self.run_pass(), ["nothing to dispatch"])

    def test_raid_members_share_one_head(self):
        for session in ("sess-1", "sess-2"):
            self.run_cli(["raid", "join", "ci", "--until-leave"], session, self.repo_dir)
        self.write_gh_fixture("view_acme-app_1", dict(OPEN_VIEW, state="MERGED", mergedAt="2026-10-04T00:00:00Z"))
        self.sync_gh("sess-1")
        self.assertEqual(self.run_pass(), ["acme: merge_head acme/app#2 -> notified beta"])
