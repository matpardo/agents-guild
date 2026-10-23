import sqlite3

from guild import locking, paths

from tests.testutil import GuildTestCase


class PartyCloseTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha"], "sess-1", self.repo_dir)
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", self.repo_dir)
        self.run_cli(["task", "add", "demo/T01", "--title", "First"], "sess-1", self.repo_dir)
        self.run_cli(["task", "done", "demo/T01", "--summary", "shipped"], "sess-1", self.repo_dir)
        self.run_cli(
            ["ask", "Ship it?", "--context", "tests green", "--ref", "task:demo/T01"], "sess-1", self.repo_dir
        )
        self.run_cli(["claim", "ci.yml", "--ttl", "8h"], "sess-1", self.repo_dir)

    def _row(self, query, params):
        conn = sqlite3.connect(str(self.data_home / "guild" / "guild.db"))
        conn.row_factory = sqlite3.Row
        row = conn.execute(query, params).fetchone()
        conn.close()
        return row

    def test_human_closes_party_by_name_and_cleans_up(self):
        code, out, err = self.run_cli(["party", "close", "alpha", "--pending", "none"], None, None)
        self.assertEqual(code, 0, err)
        self.assertIn("party 'alpha' closed: 1 quest done, 1 ask dismissed, 1 claim released", out)
        self.assertEqual(self._row("SELECT state FROM parties WHERE name = ?", ("alpha",))["state"], "closed")
        self.assertEqual(self._row("SELECT state FROM quests WHERE slug = ?", ("demo",))["state"], "done")
        self.assertEqual(self._row("SELECT state FROM asks WHERE id = 1", ())["state"], "dismissed")
        self.assertIsNone(self._row("SELECT area FROM claims WHERE area = ?", ("ci.yml",)))

    def _expired_handoff_setup(self):
        self.run_cli(["handoff", "--in-flight", "x", "--learned", "y"], "sess-1", self.repo_dir)
        self.run_cli(["party", "resume", "alpha"], "sess-2", self.repo_dir)
        self.run_cli(["handoff", "--in-flight", "x", "--learned", "y"], "sess-2", self.repo_dir)

    def test_close_reports_pruned_handoff_count_when_files_deleted(self):
        self._expired_handoff_setup()
        code, out, err = self.run_cli(["party", "close", "alpha", "--pending", "none"], None, None)
        self.assertEqual(code, 0, err)
        self.assertIn("pruned 1 handoff file(s)", out)
        self.assertFalse((self.data_home / "guild" / "handoffs" / "alpha-g1.md").exists())

    def test_close_skips_prune_silently_when_locked(self):
        self._expired_handoff_setup()
        with locking.try_lock(paths.state_dir() / "handoff-prune", "prune.lock"):
            code, out, err = self.run_cli(["party", "close", "alpha", "--pending", "none"], None, None)
        self.assertEqual(code, 0, err)
        self.assertNotIn("pruned", out)
        self.assertTrue((self.data_home / "guild" / "handoffs" / "alpha-g1.md").exists())

    def test_close_omits_pruned_line_when_nothing_deleted(self):
        code, out, err = self.run_cli(["party", "close", "alpha", "--pending", "none"], None, None)
        self.assertNotIn("pruned", out)

    def test_bound_session_closes_own_party_without_name(self):
        code, out, err = self.run_cli(["party", "close", "--pending", "none"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        self.assertIn("party 'alpha' closed", out)

    def test_session_cannot_close_another_party(self):
        self.run_cli(["party", "start", "beta"], "sess-2", self.repo_dir)
        code, out, err = self.run_cli(["party", "close", "alpha", "--pending", "none"], "sess-2", self.repo_dir)
        self.assertEqual(code, 1)
        self.assertIn("cannot close another party", err)

    def test_close_reports_open_tracked_prs(self):
        self.write_gh_fixture(
            "view_acme-app_1",
            {"state": "OPEN", "isDraft": True, "headRefName": "feature/x", "title": "t"},
        )
        self.run_cli(
            ["pr", "track", "acme/app#1", "--task", "demo/T01", "--what", "x", "--waits", "y"],
            "sess-1", self.repo_dir,
        )
        code, out, err = self.run_cli(["party", "close", "alpha", "--pending", "none"], None, None)
        self.assertEqual(code, 0, err)
        self.assertIn("tracked PRs still open: acme/app#1", out)

    def test_close_unknown_or_closed_party_fails(self):
        code, out, err = self.run_cli(["party", "close", "ghost", "--pending", "none"], None, None)
        self.assertEqual(code, 1)
        self.assertIn("unknown party 'ghost'", err)
        self.run_cli(["party", "close", "alpha", "--pending", "none"], None, None)
        code, out, err = self.run_cli(["party", "close", "alpha", "--pending", "none"], None, None)
        self.assertEqual(code, 1)
        self.assertIn("already closed", err)

    def test_closed_party_leaves_board(self):
        self.run_cli(["party", "close", "alpha", "--pending", "none"], None, None)
        code, out, err = self.run_cli(["board"], None, None)
        self.assertNotIn("━━ alpha", out)

    def test_rebuild_reproduces_cascade(self):
        self.run_cli(["party", "close", "alpha", "--pending", "none"], None, None)
        self.run_cli(["rebuild"], None, None)
        self.assertEqual(self._row("SELECT state FROM quests WHERE slug = ?", ("demo",))["state"], "done")
        self.assertEqual(self._row("SELECT state FROM asks WHERE id = 1", ())["state"], "dismissed")


class QuestDoneTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha"], "sess-1", self.repo_dir)
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", self.repo_dir)

    def test_owner_marks_quest_done(self):
        code, out, err = self.run_cli(["quest", "done", "demo"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        self.assertIn("quest 'demo' done", out)
        code, out, err = self.run_cli(["board"], None, None)
        self.assertNotIn("Demo", out)

    def test_other_party_cannot_mark_quest_done(self):
        self.run_cli(["party", "start", "beta"], "sess-2", self.repo_dir)
        code, out, err = self.run_cli(["quest", "done", "demo"], "sess-2", self.repo_dir)
        self.assertEqual(code, 1)
        self.assertIn("not owned by party 'beta'", err)

    def test_unknown_quest_fails(self):
        code, out, err = self.run_cli(["quest", "done", "ghost"], "sess-1", self.repo_dir)
        self.assertEqual(code, 1)
        self.assertIn("unknown quest 'ghost'", err)


class RaidMemberCloseTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha"], "sess-1", self.repo_dir)
        self.run_cli(["party", "start", "beta"], "sess-2", self.repo_dir)
        self.run_cli(["raid", "join", "ci", "--until-leave"], "sess-1", self.repo_dir)

    def test_close_succeeds_while_other_member_active(self):
        self.run_cli(["raid", "join", "ci", "--until-leave"], "sess-2", self.repo_dir)
        code, out, err = self.run_cli(["party", "close", "--pending", "none"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        self.assertIn("party 'alpha' closed", out)

    def test_other_member_close_unaffected(self):
        self.run_cli(["raid", "join", "ci", "--until-leave"], "sess-2", self.repo_dir)
        code, out, err = self.run_cli(["party", "close", "--pending", "none"], "sess-2", self.repo_dir)
        self.assertEqual(code, 0, err)
