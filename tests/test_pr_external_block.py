import json

from guild import db, pr_records, work_queue
from guild.commands import merge_queue as merge_queue_commands
from tests.mq_fixtures import MergeQueueTestCase


class ExternalBlockTestCase(MergeQueueTestCase):
    def setUp(self):
        super().setUp()
        self.start_party("alpha", "sess-1")
        self.run_cli(["quest", "add", "qa", "--title", "qa", "--no-epic"], "sess-1", self.repo_dir)
        for tid in ("T01", "T02", "T03"):
            self.run_cli(["task", "add", "qa/{}".format(tid), "--title", tid], "sess-1", self.repo_dir)
        for number in (1, 2, 3):
            self.track("sess-1", number, "qa/T0{}".format(number), "ready")
        self.sync_gh("sess-1")

    def pr_set(self, number, *args):
        code, out, err = self.run_cli(["pr", "set", "acme/app#{}".format(number)] + list(args), "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)

    def column(self, number):
        return self.query("SELECT blocked_external FROM prs WHERE number = {}".format(number))[0][0]

    def set_caps(self, **caps):
        config_file = self.config_home / "guild" / "projects" / "acme.json"
        data = json.loads(config_file.read_text())
        data.update(caps)
        config_file.write_text(json.dumps(data))

    def queue(self):
        code, out, err = self.run_cli(["merge-queue"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        return out

    def test_flag_sets_clears_and_survives_sync(self):
        self.pr_set(1, "--blocked-external", "team meeting")
        self.assertEqual(self.column(1), "team meeting")
        self.sync_gh("sess-1")
        self.assertEqual(self.column(1), "team meeting")
        self.pr_set(1, "--waits", "other")
        self.assertEqual(self.column(1), "team meeting")
        self.pr_set(1, "--no-blocked-external")
        self.assertIsNone(self.column(1))

    def test_empty_reason_is_rejected(self):
        code, out, err = self.run_cli(["pr", "set", "acme/app#1", "--blocked-external", " "], "sess-1", self.repo_dir)
        self.assertEqual(code, 1)

    def test_queue_shows_reason_keeps_order_and_skips_head(self):
        self.pr_set(1, "--blocked-external", "team meeting")
        lines = self.queue().splitlines()
        self.assertIn("acme/app#1", lines[1])
        self.assertIn("manual block: team meeting", lines[1])
        self.assertEqual(merge_queue_commands.next_to_merge(self.conn(), {"alpha"}), "acme/app#2")

    def test_pin_dependent_waits_externally(self):
        self.pr_set(1, "--blocked-external", "team meeting")
        self.run_cli(["merge-queue", "pin", "acme/app#1", "--before", "acme/app#2"], "sess-1", self.repo_dir)
        self.assertIn("waits on manually blocked acme/app#1: team meeting", self.queue().splitlines()[2])
        self.assertEqual(merge_queue_commands.next_to_merge(self.conn(), {"alpha"}), "acme/app#3")

    def conn(self):
        return db.connect(self.data_home / "guild" / "guild.db")

    def test_external_refs_include_transitive(self):
        self.pr_set(1, "--blocked-external", "x")
        self.run_cli(["merge-queue", "pin", "acme/app#1", "--before", "acme/app#2"], "sess-1", self.repo_dir)
        self.assertEqual(pr_records.external_blocked_refs(self.conn()), {"acme/app#1", "acme/app#2"})

    def test_caps_exclude_external_prs(self):
        self.set_caps(max_open_prs_per_party=2, max_open_prs=2)
        self.pr_set(1, "--blocked-external", "x")
        self.run_cli(["merge-queue", "pin", "acme/app#1", "--before", "acme/app#2"], "sess-1", self.repo_dir)
        ctx_conn = self.conn()
        self.assertEqual(len(work_queue._own_open_prs(ctx_conn, "alpha")), 1)
        parties = work_queue._project_parties(ctx_conn, "acme")
        self.assertEqual(len(work_queue._scope_open_prs(ctx_conn, parties)), 1)
