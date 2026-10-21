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
