from guild import db, party_progress, paths
from tests.testutil import GuildTestCase

_OPEN_VIEW = {"state": "OPEN", "isDraft": False, "headRefName": "feature/x", "title": "t"}


class PartyProgressTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha", "--reason", "test reason"], "sess-1", self.repo_dir)

    def _cli(self, args):
        code, out, err = self.run_cli(args, "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)

    def _remaining(self):
        conn = db.connect(paths.db_path())
        try:
            return party_progress.remaining(conn, "alpha")
        finally:
            conn.close()

    def _add_quest(self, slug, tasks):
        self._cli(["quest", "add", slug, "--title", slug, "--no-epic", "--tasks", ",".join(tasks)])

    def _track_loose(self, number):
        self.write_gh_fixture("view_acme-app_{}".format(number), _OPEN_VIEW)
        self.track_legacy_card_pr("alpha", "acme/app", number, "ABC-1", "w", "r", "feature/x")

    def test_counts_queued_active_blocked_and_done(self):
        self._add_quest("demo", ["A", "B", "C", "D"])
        self._cli(["task", "start", "demo/A"])
        self._cli(["task", "start", "demo/B"])
        self._cli(["task", "block", "demo/B", "--reason", "wait"])
        self._cli(["task", "start", "demo/C"])
        self._cli(["task", "done", "demo/C", "--summary", "ok"])
        result = self._remaining()
        self.assertEqual((result["active"], result["blocked"], result["queued"], result["pending"]), (1, 1, 1, 3))
        self.assertEqual(result["quests"], [{"slug": "demo", "done": 1, "total": 4}])
        self.assertFalse(result["all_done"])

    def test_sums_two_quests(self):
        self._add_quest("one", ["A", "B"])
        self._add_quest("two", ["C"])
        result = self._remaining()
        self.assertEqual(result["pending"], 3)
        self.assertEqual([quest["slug"] for quest in result["quests"]], ["one", "two"])

    def test_ignores_done_quest(self):
        self._add_quest("demo", ["A"])
        self._cli(["task", "start", "demo/A"])
        self._cli(["task", "done", "demo/A", "--summary", "ok"])
        self._cli(["quest", "done", "demo", "--force"])
        result = self._remaining()
        self.assertEqual(result["quests"], [])
        self.assertTrue(result["all_done"])

    def test_loose_open_pr_counts_as_extra(self):
        self._track_loose(1)
        result = self._remaining()
        self.assertEqual(result["extra_prs"], 1)
        self.assertEqual(result["pending"], 0)
        self.assertFalse(result["all_done"])

    def test_merged_loose_pr_does_not_count(self):
        self._track_loose(1)
        self.write_gh_fixture("view_acme-app_1", dict(_OPEN_VIEW, state="MERGED", mergedAt="2026-01-01T00:00:00Z"))
        self._cli(["sync", "--source", "gh"])
        result = self._remaining()
        self.assertEqual(result["extra_prs"], 0)
        self.assertTrue(result["all_done"])

    def test_pr_on_own_quest_task_is_not_extra(self):
        self._add_quest("demo", ["A"])
        self._cli(["task", "start", "demo/A"])
        self.write_gh_fixture("view_acme-app_2", _OPEN_VIEW)
        self._cli(["pr", "track", "acme/app#2", "--task", "demo/A", "--what", "w", "--waits", "r"])
        self.assertEqual(self._remaining()["extra_prs"], 0)

    def test_party_without_work_is_all_done(self):
        result = self._remaining()
        self.assertEqual(result["pending"], 0)
        self.assertEqual(result["extra_prs"], 0)
        self.assertTrue(result["all_done"])
