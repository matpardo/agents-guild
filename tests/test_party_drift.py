from tests.test_drift import DriftTestCase


class PartyDriftTestCase(DriftTestCase):
    def setUp(self):
        super().setUp()
        self.write_session(2, "sess-2", "beta-session")
        self.run_cli(["party", "start", "beta", "--reason", "test reason"], "sess-2", self.repo_dir)
        self._write_epic(
            "wave9", "status: active\n",
            "## T01 — First\n\n**JIRA:** DEMO-90\n**Deps:** —\n**Status:** [ ] pending\n",
        )
        self._sync_sdd()
        self.run_cli(
            ["quest", "add", "wave9", "--title", "Wave 9", "--epic", "wave9", "--tasks", "T01"],
            "sess-1", self.repo_dir,
        )

    def _start_task(self):
        return self.run_cli(["task", "start", "wave9/T01", "--summary", "go"], "sess-1", self.repo_dir)


class TaskStartNudgeTests(PartyDriftTestCase):
    def test_new_card_nudges_the_move(self):
        self._record_cards([self._card("DEMO-90", "new")])
        code, out, err = self._start_task()
        self.assertEqual(code, 0, err)
        self.assertIn("move DEMO-90 to In Progress", out)

    def test_started_card_stays_silent(self):
        self._record_cards([self._card("DEMO-90", "indeterminate")])
        code, out, err = self._start_task()
        self.assertNotIn("move", out)


class BriefDriftTests(PartyDriftTestCase):
    def test_owner_sees_drift(self):
        self._record_cards([self._card("DEMO-90", "new")])
        self._start_task()
        code, out, err = self.run_cli(["brief"], "sess-1", self.repo_dir)
        self.assertIn("drift:", out)
        self.assertIn("move DEMO-90 to In Progress", out)

    def test_no_drift_is_silent(self):
        self._record_cards([self._card("DEMO-90", "indeterminate")])
        self._start_task()
        code, out, err = self.run_cli(["brief"], "sess-1", self.repo_dir)
        self.assertNotIn("drift:", out)

    def test_other_party_does_not_see_it(self):
        self._record_cards([self._card("DEMO-90", "new")])
        self._start_task()
        code, out, err = self.run_cli(["brief"], "sess-2", self.repo_dir)
        self.assertNotIn("drift:", out)
        self.assertNotIn("DEMO-90", out)

    def test_list_is_capped(self):
        self._record_cards([self._card("DEMO-90", "new")])
        for number in range(1, 8):
            self._track_pr(number, "wave9", "T01")
        code, out, err = self.run_cli(["brief"], "sess-1", self.repo_dir)
        self.assertEqual(out.count("not started"), 5)
        self.assertIn("2 more: guild drift", out)


class NextDriftTests(PartyDriftTestCase):
    def test_drift_is_the_item_before_the_next_task(self):
        self._record_cards([self._card("DEMO-90", "new")])
        self._start_task()
        self.run_cli(["task", "add", "wave9/T02", "--title", "Second"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["next"], "sess-1", self.repo_dir)
        self.assertIn("update tracker/SDD: task:wave9/T01 started", out)
        self.assertNotIn("T02", out)

    def test_all_lists_drift_and_task(self):
        self._record_cards([self._card("DEMO-90", "new")])
        self._start_task()
        self.run_cli(["task", "add", "wave9/T02", "--title", "Second"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["next", "--all"], "sess-1", self.repo_dir)
        self.assertIn("update tracker/SDD: ", out)
        self.assertIn("task wave9/T02", out)

    def test_no_drift_is_silent(self):
        self._record_cards([self._card("DEMO-90", "indeterminate")])
        self._start_task()
        code, out, err = self.run_cli(["next"], "sess-1", self.repo_dir)
        self.assertNotIn("update tracker/SDD", out)

    def test_other_party_does_not_see_it(self):
        self._record_cards([self._card("DEMO-90", "new")])
        self._start_task()
        code, out, err = self.run_cli(["next"], "sess-2", self.repo_dir)
        self.assertNotIn("update tracker/SDD", out)


class MergeNoticeMovesTests(PartyDriftTestCase):
    def setUp(self):
        super().setUp()
        self.run_cli(["raid", "join", "release", "--ttl", "1h"], "sess-1", self.repo_dir)
        self.run_cli(["raid", "join", "release", "--ttl", "1h"], "sess-2", self.repo_dir)
        self._track_pr(1, "wave9", "T01")
        self.write_gh_fixture(
            "view_acme-app_1",
            {
                "state": "MERGED", "isDraft": False, "headRefName": "feature/1", "title": "t",
                "mergedAt": "2026-01-01T00:00:00Z", "statusCheckRollup": [],
            },
        )

    def _notice_seen_by_beta(self):
        self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)
        return self.run_cli(["inbox", "--since-last"], "sess-2", self.repo_dir)[1]

    def test_open_card_and_sdd_task_are_named(self):
        self._record_cards([self._card("DEMO-90", "indeterminate")])
        out = self._notice_seen_by_beta()
        self.assertIn("move DEMO-90 to Done; mark T01 done in wave9 tasks.md", out)

    def test_done_card_and_sdd_task_stay_silent(self):
        self._record_cards([self._card("DEMO-90", "done")])
        self._write_epic(
            "wave9", "status: active\n",
            "## T01 — First\n\n**JIRA:** DEMO-90\n**Deps:** —\n**Status:** [x] done\n",
        )
        self._sync_sdd()
        out = self._notice_seen_by_beta()
        self.assertIn("acme/app#1 merged in main", out)
        self.assertNotIn("follow-up", out)
