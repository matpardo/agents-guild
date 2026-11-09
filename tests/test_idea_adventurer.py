from guild import db, paths
from tests.mq_fixtures import OPEN_VIEW
from tests.test_adventurer import AdventurerTestCase


class IdeaAdventurerLinkTests(AdventurerTestCase):
    def setUp(self):
        super().setUp()
        self.start("adv-1", "fix typo", "--task", "demo-epic/T02")
        self.cli(["idea", "add", "Dark mode", "--description", "d"], None)

    def _links(self):
        conn = db.connect(paths.db_path())
        self.addCleanup(conn.close)
        return [row["adventurer"] for row in conn.execute("SELECT adventurer FROM idea_adventurer_links ORDER BY 1")]

    def _track_pr(self):
        self.write_gh_fixture("view_acme-app_7", dict(OPEN_VIEW))
        code, out, err = self.cli(
            ["pr", "track", "acme/app#7", "--task", "demo-epic/T02", "--what", "typo", "--waits", "review"], "adv-1"
        )
        self.assertEqual(code, 0, err)

    def test_adventurer_links_and_unlinks_its_own_idea(self):
        code, out, err = self.cli(["idea", "link", "1"], "adv-1")
        self.assertEqual(code, 0, err)
        self.assertIn("linked to adventurer 1", out)
        self.assertEqual(self._links(), [1])
        code, out, err = self.cli(["idea", "unlink", "1"], "adv-1")
        self.assertEqual(code, 0, err)
        self.assertEqual(self._links(), [])

    def test_link_twice_is_refused(self):
        self.cli(["idea", "link", "1"], "adv-1")
        code, out, err = self.cli(["idea", "link", "1"], "adv-1")
        self.assertEqual(code, 1)
        self.assertIn("already linked to adventurer 1", err)

    def test_unlink_without_a_link_is_refused(self):
        code, out, err = self.cli(["idea", "unlink", "1"], "adv-1")
        self.assertEqual(code, 1)
        self.assertIn("not linked to adventurer 1", err)

    def test_unlink_is_refused_once_the_adventurer_tracks_a_pr(self):
        self.cli(["idea", "link", "1"], "adv-1")
        self._track_pr()
        code, out, err = self.cli(["idea", "unlink", "1"], "adv-1")
        self.assertEqual(code, 1)
        self.assertIn("the adventurer already tracks a PR", err)
        self.assertEqual(self._links(), [1])

    def test_unknown_idea_is_refused(self):
        self.assertEqual(self.cli(["idea", "link", "9"], "adv-1")[0], 1)

    def test_human_needs_a_holder_flag(self):
        self.assertEqual(self.cli(["idea", "link", "1"], None)[0], 1)
        code, out, err = self.cli(["idea", "link", "1", "--party", "x", "--adventurer", "1"], None)
        self.assertEqual(code, 1)
        self.assertIn("--party <name> or --adventurer <id>", err)
        self.assertEqual(self.cli(["idea", "link", "1", "--adventurer", "1"], None)[0], 0)
        self.assertEqual(self._links(), [1])
        self.assertEqual(self.cli(["idea", "unlink", "1", "--adventurer", "1"], None)[0], 0)

    def test_human_cannot_link_unknown_or_done_adventurers(self):
        code, out, err = self.cli(["idea", "link", "1", "--adventurer", "9"], None)
        self.assertEqual(code, 1)
        self.assertIn("unknown adventurer 9", err)
        self.cli(["adventurer", "done", "--pending", "none"], "adv-1")
        code, out, err = self.cli(["idea", "link", "1", "--adventurer", "1"], None)
        self.assertEqual(code, 1)
        self.assertIn("adventurer 1 is done", err)

    def test_adventurer_session_cannot_act_for_others(self):
        self.assertEqual(self.cli(["idea", "link", "1", "--party", "alpha"], "adv-1")[0], 1)
        code, out, err = self.cli(["idea", "link", "1", "--adventurer", "2"], "adv-1")
        self.assertEqual(code, 1)
        self.assertIn("only for its own adventurer 1", err)
        self.assertEqual(self.cli(["idea", "link", "1", "--adventurer", "1"], "adv-1")[0], 0)

    def test_party_session_cannot_pass_adventurer(self):
        self.cli(
            ["party", "start", "alpha", "--reason", "test reason", "--goal", "test goal", "--done-when", "test done"],
            "sess-1",
        )
        code, out, err = self.cli(["idea", "link", "1", "--adventurer", "1"], "sess-1")
        self.assertEqual(code, 1)
        self.assertIn("only for its own party 'alpha'", err)

    def test_listing_shows_adventurer_and_its_state(self):
        self.cli(["idea", "link", "1"], "adv-1")
        self.assertIn("worked by: adventurer 1", self.cli(["ideas"], None)[1])
        self.cli(["adventurer", "done", "--pending", "none"], "adv-1")
        self.assertIn("worked by: adventurer 1 (done)", self.cli(["ideas", "1"], None)[1])

    def test_delete_removes_links_and_rebuild_keeps_them(self):
        self.cli(["idea", "link", "1"], "adv-1")
        self.cli(["rebuild"], None)
        self.assertEqual(self._links(), [1])
        self.cli(["idea", "delete", "1"], None)
        self.assertEqual(self._links(), [])

    def test_promote_moves_the_link_to_the_party(self):
        self.cli(["idea", "link", "1"], "adv-1")
        code, out, err = self.cli(
            ["adventurer", "promote", "alpha", "--reason", "grew", "--goal", "test goal", "--done-when", "test done"],
            "adv-1",
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(self._links(), [])
        self.assertIn("worked by: alpha", self.cli(["ideas", "1"], None)[1])
        self.cli(["rebuild"], None)
        self.assertEqual(self._links(), [])
        self.assertIn("worked by: alpha", self.cli(["ideas", "1"], None)[1])

    def test_done_report_and_board_list_the_idea(self):
        self.cli(["idea", "link", "1"], "adv-1")
        self.assertIn("ideas: #1 Dark mode", self.cli(["board"], None)[1])
        code, out, err = self.cli(["adventurer", "done", "--pending", "none"], "adv-1")
        self.assertEqual(code, 0, err)
        self.assertIn("idea #1: Dark mode", out)
        self.assertIn("ideas: #1 Dark mode", self.cli(["board"], None)[1])
