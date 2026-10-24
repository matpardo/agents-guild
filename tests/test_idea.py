from guild import context, db, origin, paths, timeutil
from guild.commands import board as board_commands
from tests.testutil import GuildTestCase


class IdeaTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])

    def _add(self, title, *extra):
        return self.run_cli(["idea", "add", title, "--description", "d " + title] + list(extra), None, None)

    def test_add_then_show(self):
        code, out, err = self._add("Dark mode", "--requester", "ana", "--deadline", "2099-01-31", "--project", "acme")
        self.assertEqual(code, 0, err)
        self.assertIn("idea #1 added", out)
        code, out, err = self.run_cli(["ideas", "1"], None, None)
        self.assertEqual(code, 0, err)
        for expected in ("Dark mode", "d Dark mode", "ana", "2099-01-31", "acme"):
            self.assertIn(expected, out)

    def test_add_rejects_bad_input(self):
        for extra in (["--deadline", "31-01-2099"], ["--deadline", "2099-13-01"], ["--project", "ghost"]):
            code, out, err = self._add("x", *extra)
            self.assertEqual(code, 1, extra)
        code, out, err = self.run_cli(["idea", "add", "  ", "--description", "d"], None, None)
        self.assertEqual(code, 1)
        code, out, err = self.run_cli(["idea", "add", "t", "--description", "mail me@x.com"], None, None)
        self.assertEqual(code, 1)
        self.assertEqual(self.run_cli(["ideas"], None, None)[1].strip(), "no ideas")

    def test_list_sorts_by_deadline_nulls_last_and_marks_overdue(self):
        self._add("none")
        self._add("late", "--deadline", "2099-12-01")
        self._add("soon", "--deadline", "2099-01-01")
        self._add("past", "--deadline", "2000-01-01")
        code, out, err = self.run_cli(["ideas"], None, None)
        titles = [line for line in out.splitlines()]
        order = [next(i for i, line in enumerate(titles) if name in line) for name in ("past", "soon", "late", "none")]
        self.assertEqual(order, sorted(order))
        self.assertIn("overdue", titles[order[0]])
        self.assertNotIn("overdue", titles[order[1]])

    def test_list_filters_by_project(self):
        self._add("a", "--project", "acme")
        self._add("b")
        code, out, err = self.run_cli(["ideas", "--project", "acme"], None, None)
        self.assertIn("a", out)
        self.assertNotIn(" b", out)

    def test_edit_changes_only_given_fields_and_clears(self):
        self._add("t", "--requester", "ana", "--deadline", "2099-01-01")
        code, out, err = self.run_cli(["idea", "edit", "1", "--title", "new", "--no-deadline"], None, None)
        self.assertEqual(code, 0, err)
        out = self.run_cli(["ideas", "1"], None, None)[1]
        self.assertIn("new", out)
        self.assertIn("ana", out)
        self.assertNotIn("2099", out)

    def test_edit_errors(self):
        self._add("t")
        self.assertEqual(self.run_cli(["idea", "edit", "1"], None, None)[0], 1)
        self.assertEqual(self.run_cli(["idea", "edit", "9", "--title", "x"], None, None)[0], 1)
        self.assertEqual(self.run_cli(["idea", "edit", "1", "--deadline", "nope"], None, None)[0], 1)
        self.assertEqual(self.run_cli(["idea", "edit", "1", "--project", "ghost"], None, None)[0], 1)
        self.assertEqual(self.run_cli(["idea", "edit", "1", "--title", " "], None, None)[0], 1)
        self.assertEqual(self.run_cli(["idea", "edit", "1", "--deadline", "2099-01-01", "--no-deadline"], None, None)[0], 2)

    def test_delete(self):
        self._add("t")
        code, out, err = self.run_cli(["idea", "delete", "1"], None, None)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.run_cli(["idea", "delete", "1"], None, None)[0], 1)
        self.assertEqual(self.run_cli(["ideas", "1"], None, None)[0], 1)

    def test_rebuild_replays_edits_and_deletes(self):
        self._add("one")
        self._add("two")
        self.run_cli(["idea", "edit", "1", "--title", "uno"], None, None)
        self.run_cli(["idea", "delete", "2"], None, None)
        self.run_cli(["rebuild"], None, None)
        out = self.run_cli(["ideas"], None, None)[1]
        self.assertIn("uno", out)
        self.assertNotIn("two", out)

    def test_ids_are_not_reused_after_delete_of_older_idea(self):
        self._add("one")
        self._add("two")
        self.run_cli(["idea", "delete", "1"], None, None)
        self.assertIn("idea #3 added", self._add("three")[1])


class IdeaLinkTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha", "--reason", "test reason"], "sess-1", self.repo_dir)
        self.run_cli(["party", "start", "beta", "--reason", "test reason"], "sess-2", self.repo_dir)
        self.run_cli(["idea", "add", "Dark mode", "--description", "d"], None, None)

    def _links(self):
        conn = db.connect(paths.db_path())
        self.addCleanup(conn.close)
        return [row["party"] for row in conn.execute("SELECT party FROM idea_links ORDER BY party")]

    def test_session_links_and_unlinks_its_own_party(self):
        code, out, err = self.run_cli(["idea", "link", "1"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        self.assertEqual(self._links(), ["alpha"])
        code, out, err = self.run_cli(["idea", "unlink", "1"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        self.assertEqual(self._links(), [])

    def test_human_needs_party_flag(self):
        self.assertEqual(self.run_cli(["idea", "link", "1"], None, None)[0], 1)
        code, out, err = self.run_cli(["idea", "link", "1", "--party", "beta"], None, None)
        self.assertEqual(code, 0, err)
        self.assertEqual(self._links(), ["beta"])
        self.assertEqual(self.run_cli(["idea", "unlink", "1"], None, None)[0], 1)
        self.assertEqual(self.run_cli(["idea", "unlink", "1", "--party", "beta"], None, None)[0], 0)

    def test_session_cannot_act_for_another_party(self):
        self.assertEqual(self.run_cli(["idea", "link", "1", "--party", "beta"], "sess-1", self.repo_dir)[0], 1)
        self.assertEqual(self.run_cli(["idea", "link", "1", "--party", "alpha"], "sess-1", self.repo_dir)[0], 0)

    def test_unbound_session_is_refused(self):
        self.assertEqual(self.run_cli(["idea", "link", "1"], "sess-x", self.repo_dir)[0], 1)

    def test_refusals(self):
        self.assertEqual(self.run_cli(["idea", "link", "9"], "sess-1", self.repo_dir)[0], 1)
        self.assertEqual(self.run_cli(["idea", "link", "1", "--party", "ghost"], None, None)[0], 1)
        self.run_cli(["idea", "link", "1"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["idea", "link", "1"], "sess-1", self.repo_dir)
        self.assertEqual(code, 1)
        self.assertIn("already linked", err)
        self.assertEqual(self.run_cli(["idea", "unlink", "1", "--party", "beta"], None, None)[0], 1)

    def test_closed_party_cannot_be_linked(self):
        self.run_cli(["party", "close", "--pending", "none"], "sess-2", self.repo_dir)
        self.assertEqual(self.run_cli(["idea", "link", "1", "--party", "beta"], None, None)[0], 1)

    def test_ideas_show_worked_by_and_mark_closed(self):
        self.run_cli(["idea", "link", "1"], "sess-1", self.repo_dir)
        self.run_cli(["idea", "link", "1"], "sess-2", self.repo_dir)
        self.run_cli(["party", "close", "--pending", "none"], "sess-2", self.repo_dir)
        for argv in (["ideas"], ["ideas", "1"]):
            out = self.run_cli(argv, None, None)[1]
            self.assertIn("worked by: alpha, beta (closed)", out)

    def test_board_lists_ideas_per_party(self):
        self.run_cli(["idea", "link", "1"], "sess-1", self.repo_dir)
        out = self.run_cli(["board"], None, None)[1]
        self.assertIn("ideas: #1 Dark mode", out)

    def test_board_model_carries_links(self):
        self.run_cli(["idea", "link", "1"], "sess-1", self.repo_dir)
        model = board_commands.board_model(self._ctx())
        self.assertEqual(model["ideas"][0]["parties"], [{"name": "alpha", "state": "active"}])
        by_name = {party["name"]: party for party in model["parties"]}
        self.assertEqual(by_name["alpha"]["ideas"], [{"id": 1, "title": "Dark mode"}])
        self.assertEqual(by_name["beta"]["ideas"], [])

    def _ctx(self):
        return context.RunContext(
            db.connect(paths.db_path()), None, self.repo_dir, timeutil.utcnow(), origin.current_origin(),
            self.sessions_dir, self.config_home / "guild" / "projects", None,
        )

    def test_delete_removes_links_and_rebuild_keeps_them(self):
        self.run_cli(["idea", "add", "Two", "--description", "d"], None, None)
        self.run_cli(["idea", "link", "1"], "sess-1", self.repo_dir)
        self.run_cli(["idea", "link", "2", "--party", "beta"], None, None)
        self.run_cli(["rebuild"], None, None)
        self.assertEqual(self._links(), ["alpha", "beta"])
        self.run_cli(["idea", "unlink", "2", "--party", "beta"], None, None)
        self.run_cli(["idea", "delete", "1"], None, None)
        self.assertEqual(self._links(), [])
        self.run_cli(["rebuild"], None, None)
        self.assertEqual(self._links(), [])
