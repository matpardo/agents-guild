import sqlite3

from tests.mq_fixtures import TASKS_MD, MergeQueueTestCase


class PinTestCase(MergeQueueTestCase):
    def setUp(self):
        super().setUp()
        for name, session in (("alpha", "sess-1"), ("beta", "sess-2"), ("gamma", "sess-3")):
            self.start_party(name, session)
        code, out, err = self.sync_sdd(self.repo_dir, "sess-1", "acme", "demo-epic", TASKS_MD)
        self.assertEqual(code, 0, err)
        self.add_quest("sess-1", "qa", "demo-epic", "T01,T03")
        self.add_quest("sess-2", "qb", "demo-epic", "T02")
        self.run_cli(["quest", "add", "qc", "--title", "qc", "--no-epic"], "sess-3", self.repo_dir)
        for tid in ("T01", "T02", "T03"):
            self.run_cli(["task", "add", "qc/{}".format(tid), "--title", tid], "sess-3", self.repo_dir)
        self.track("sess-1", 1, "qa/T01", "ready")
        self.track("sess-1", 2, "qa/T03", "ready")
        self.track("sess-2", 3, "qb/T02", "ready")
        self.track("sess-2", 6, "qb/T02", "ready")
        self.track("sess-3", 4, "qc/T01", "ready")
        self.track("sess-3", 5, "qc/T02", "ready")
        self.run_cli(["raid", "join", "ci", "--until-leave"], "sess-1", self.repo_dir)
        self.run_cli(["raid", "join", "ci", "--until-leave"], "sess-2", self.repo_dir)

    def pin(self, session_id, first, second):
        return self.run_cli(
            ["merge-queue", "pin", "acme/app#{}".format(first), "--before", "acme/app#{}".format(second)],
            session_id, self.repo_dir,
        )

    def unpin(self, session_id, first, second):
        return self.run_cli(
            ["merge-queue", "unpin", "acme/app#{}".format(first), "--before", "acme/app#{}".format(second)],
            session_id, self.repo_dir,
        )

    def pins(self):
        rows = self.query(
            "SELECT first_number, second_number, party FROM merge_queue_pins ORDER BY first_number"
        )
        return [(row["first_number"], row["second_number"], row["party"]) for row in rows]


class PinAuthorityTests(PinTestCase):
    def test_raid_member_pins_prs_of_two_members(self):
        code, out, err = self.pin("sess-1", 2, 3)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.pins(), [(2, 3, "alpha")])

    def test_raid_member_pins_its_own_prs(self):
        code, out, err = self.pin("sess-1", 1, 2)
        self.assertEqual(code, 0, err)

    def test_other_raid_member_pins_prs_of_two_members(self):
        code, out, err = self.pin("sess-2", 3, 1)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.pins(), [(3, 1, "beta")])

    def test_member_of_the_raid_owning_neither_pr_pins(self):
        self.run_cli(["raid", "join", "ci", "--until-leave"], "sess-3", self.repo_dir)
        code, out, err = self.pin("sess-3", 2, 3)
        self.assertEqual(code, 0, err)

    def test_party_outside_the_shared_raid_is_rejected(self):
        code, out, err = self.pin("sess-3", 2, 3)
        self.assertEqual(code, 1)
        self.assertIn("raid 'ci'", err)
        self.assertIn("active member", err)
        self.assertEqual(self.pins(), [])

    def test_human_pins_inside_a_raid(self):
        code, out, err = self.pin(None, 3, 2)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.pins(), [(3, 2, None)])

    def test_party_outside_raids_pins_its_own_prs(self):
        code, out, err = self.pin("sess-3", 4, 5)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.pins(), [(4, 5, "gamma")])

    def test_party_cannot_pin_a_pr_it_does_not_own(self):
        code, out, err = self.pin("sess-3", 4, 1)
        self.assertEqual(code, 1)
        self.assertIn("party 'gamma' does not own both PRs", err)

    def test_raid_member_cannot_pin_across_the_raid_boundary(self):
        code, out, err = self.pin("sess-1", 1, 4)
        self.assertEqual(code, 1)
        self.assertIn("party 'alpha' does not own both PRs", err)

    def test_human_pins_across_parties(self):
        code, out, err = self.pin(None, 1, 4)
        self.assertEqual(code, 0, err)

    def test_unbound_session_is_not_the_human(self):
        code, out, err = self.pin("sess-unbound", 1, 4)
        self.assertEqual(code, 1)
        self.assertIn("session not bound", err)

    def test_unpin_follows_the_same_authority(self):
        self.pin(None, 3, 2)
        code, out, err = self.unpin("sess-3", 3, 2)
        self.assertEqual(code, 1)
        self.assertIn("active member", err)
        code, out, err = self.unpin("sess-1", 3, 2)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.pins(), [])

    def test_member_that_left_the_raid_loses_authority(self):
        self.run_cli(["raid", "leave", "ci"], "sess-1", self.repo_dir)
        code, out, err = self.pin("sess-1", 2, 3)
        self.assertEqual(code, 1)
        self.assertIn("does not own both PRs", err)


class PinValidationTests(PinTestCase):
    def test_untracked_pr_is_rejected(self):
        code, out, err = self.run_cli(
            ["merge-queue", "pin", "acme/app#99", "--before", "acme/app#1"], None, self.repo_dir
        )
        self.assertEqual(code, 1)
        self.assertIn("PR 'acme/app#99' is not tracked", err)

    def test_closed_pr_is_rejected(self):
        self.write_gh_fixture(
            "view_acme-app_3",
            {
                "state": "MERGED", "isDraft": False, "headRefName": "f", "title": "t",
                "mergedAt": "2026-01-01T00:00:00Z", "statusCheckRollup": [],
            },
        )
        self.sync_gh("sess-1")
        code, out, err = self.pin(None, 3, 2)
        self.assertEqual(code, 1)
        self.assertIn("PR 'acme/app#3' is merged: only open PRs can be pinned", err)

    def test_pin_before_itself_is_rejected(self):
        code, out, err = self.pin(None, 1, 1)
        self.assertEqual(code, 1)
        self.assertIn("cannot pin", err)

    def test_invalid_ref_is_rejected(self):
        code, out, err = self.run_cli(
            ["merge-queue", "pin", "nope", "--before", "acme/app#1"], None, self.repo_dir
        )
        self.assertEqual(code, 1)
        self.assertIn("invalid PR ref", err)

    def test_duplicate_pin_is_rejected(self):
        self.pin(None, 3, 2)
        code, out, err = self.pin(None, 3, 2)
        self.assertEqual(code, 1)
        self.assertIn("already pinned", err)

    def test_opposite_pin_is_a_cycle_naming_it(self):
        self.pin(None, 3, 2)
        code, out, err = self.pin(None, 2, 3)
        self.assertEqual(code, 1)
        self.assertIn("cycle: acme/app#2 -> acme/app#3 -> acme/app#2", err)
        self.assertEqual(len(self.pins()), 1)

    def test_longer_pin_cycle_is_named(self):
        self.pin(None, 2, 3)
        self.pin(None, 3, 4)
        code, out, err = self.pin(None, 4, 2)
        self.assertEqual(code, 1)
        self.assertIn("cycle: acme/app#4 -> acme/app#2 -> acme/app#3 -> acme/app#4", err)

    def test_pin_against_a_task_dependency_is_a_cycle(self):
        code, out, err = self.pin(None, 1, 3)
        self.assertEqual(code, 1)
        self.assertIn("cycle: acme/app#1 -> acme/app#3 -> acme/app#1", err)

    def test_pin_inverting_a_stack_is_a_cycle(self):
        conn = sqlite3.connect(str(self.data_home / "guild" / "guild.db"))
        conn.execute("UPDATE prs SET branch = 'feat/base' WHERE number = 2")
        conn.execute("UPDATE prs SET base_branch = 'feat/base' WHERE number = 3")
        conn.commit()
        conn.close()
        code, out, err = self.pin(None, 3, 2)
        self.assertEqual(code, 1)
        self.assertIn("cycle: acme/app#3 -> acme/app#2 -> acme/app#3", err)

    def test_pin_along_a_task_dependency_is_accepted(self):
        code, out, err = self.pin(None, 3, 1)
        self.assertEqual(code, 0, err)

    def test_unpin_of_a_missing_pin_is_an_error(self):
        code, out, err = self.unpin(None, 3, 2)
        self.assertEqual(code, 1)
        self.assertIn("no pin of 'acme/app#3' before 'acme/app#2'", err)

    def test_unpin_still_works_after_a_pr_closes(self):
        self.pin(None, 3, 2)
        self.write_gh_fixture(
            "view_acme-app_3",
            {
                "state": "MERGED", "isDraft": False, "headRefName": "f", "title": "t",
                "mergedAt": "2026-01-01T00:00:00Z", "statusCheckRollup": [],
            },
        )
        self.sync_gh("sess-1")
        code, out, err = self.unpin(None, 3, 2)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.pins(), [])

    def test_pin_and_unpin_do_not_touch_github(self):
        (self.gh_fixtures_dir / "view_acme-app_3.json").unlink()
        (self.gh_fixtures_dir / "view_acme-app_2.json").unlink()
        code, out, err = self.pin(None, 3, 2)
        self.assertEqual(code, 0, err)
        code, out, err = self.unpin(None, 3, 2)
        self.assertEqual(code, 0, err)


class PinEventTests(PinTestCase):
    def test_events_carry_the_author(self):
        self.pin("sess-1", 2, 3)
        self.unpin("sess-1", 2, 3)
        self.pin(None, 3, 2)
        rows = self.query(
            "SELECT kind, party, payload FROM events WHERE kind LIKE 'merge_queue.%' ORDER BY seq"
        )
        self.assertEqual(
            [(row["kind"], row["party"]) for row in rows],
            [("merge_queue.pinned", "alpha"), ("merge_queue.unpinned", "alpha"), ("merge_queue.pinned", None)],
        )

    def test_rebuild_reproduces_pins(self):
        self.pin("sess-1", 2, 3)
        self.pin(None, 3, 4)
        self.pin(None, 4, 5)
        self.unpin(None, 4, 5)
        before = self.pins()
        code, out, err = self.run_cli(["rebuild"], None, None)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.pins(), before)
        self.assertEqual(before, [(2, 3, "alpha"), (3, 4, None)])
