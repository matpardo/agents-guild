from datetime import timedelta
from unittest import mock

from guild import db, paths, timeutil
from tests.testutil import GuildTestCase


class QuestAddValidationTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(
            ["party", "start", "alpha", "--reason", "test reason", "--goal", "test goal", "--done-when", "test done"],
            "sess-1",
            self.repo_dir,
        )

    def test_quest_add_without_project_fails(self):
        code, out, err = self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", self.root)
        self.assertEqual(code, 1)
        self.assertIn("no project config matches", err)

    def test_epic_quest_requires_synced_epic(self):
        code, out, err = self.run_cli(
            [
                "quest",
                "add",
                "demo",
                "--title",
                "Demo",
                "--epic",
                "compliance",
                "--tasks",
                "T01,T02",
            ],
            "sess-1",
            self.repo_dir,
        )
        self.assertEqual(code, 1)
        self.assertIn("never synced", err)
        self.assertIn("guild sync --source sdd", err)

    def test_epic_quest_without_tasks_is_empty(self):
        self.sync_sdd(self.repo_dir, "sess-1", "acme", "compliance", "## T01 — First task\n\n**Deps:** —\n")
        code, out, err = self.run_cli(
            ["quest", "add", "demo", "--title", "Demo", "--epic", "compliance"], "sess-1", self.repo_dir
        )
        self.assertEqual(code, 0, err)
        code, out, err = self.run_cli(["board"], "sess-1", self.repo_dir)
        self.assertNotIn("queued:", out)

    def test_quest_without_epic_or_no_epic_fails(self):
        code, out, err = self.run_cli(["quest", "add", "demo", "--title", "Demo"], "sess-1", self.repo_dir)
        self.assertEqual(code, 1)
        self.assertIn("--epic", err)

    def test_no_epic_cannot_combine_with_epic(self):
        code, out, err = self.run_cli(
            ["quest", "add", "demo", "--title", "Demo", "--no-epic", "--epic", "x"],
            "sess-1",
            self.repo_dir,
        )
        self.assertEqual(code, 1)

    def test_epic_quest_created_with_queued_tasks(self):
        self.sync_sdd(
            self.repo_dir,
            "sess-1",
            "acme",
            "compliance",
            "## T01 — First task\n\n**Deps:** —\n\n**Status:** [ ] pending\n\n"
            "## T02 — Second task\n\n**Deps:** —\n\n**Status:** [ ] pending\n",
        )
        code, out, err = self.run_cli(
            [
                "quest",
                "add",
                "demo",
                "--title",
                "Demo",
                "--epic",
                "compliance",
                "--tasks",
                "T01,T02",
            ],
            "sess-1",
            self.repo_dir,
        )
        self.assertEqual(code, 0)
        code, out, err = self.run_cli(["board"], "sess-1", self.repo_dir)
        self.assertIn("queued: T01, T02", out)

    def test_epic_quest_rejects_unknown_tid(self):
        self.sync_sdd(
            self.repo_dir,
            "sess-1",
            "acme",
            "compliance",
            "## T01 — First task\n\n**Deps:** —\n\n**Status:** [ ] pending\n",
        )
        code, out, err = self.run_cli(
            [
                "quest",
                "add",
                "demo",
                "--title",
                "Demo",
                "--epic",
                "compliance",
                "--tasks",
                "T01,T99",
            ],
            "sess-1",
            self.repo_dir,
        )
        self.assertEqual(code, 1)
        self.assertIn("T99", err)
        self.assertIn("not found in epic", err)

    def test_epic_quest_copies_real_titles(self):
        self.sync_sdd(
            self.repo_dir,
            "sess-1",
            "acme",
            "compliance",
            "## T01 — Configure retries\n\n**Deps:** —\n\n**Status:** [ ] pending\n",
        )
        self.run_cli(
            ["quest", "add", "demo", "--title", "Demo", "--epic", "compliance", "--tasks", "T01"],
            "sess-1",
            self.repo_dir,
        )
        self.run_cli(["task", "start", "demo/T01"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["board"], "sess-1", self.repo_dir)
        self.assertIn("Configure retries", out)

    def test_no_epic_quest_created_without_tasks(self):
        code, out, err = self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0)

    def test_no_epic_quest_created_with_tasks_using_ids_as_titles(self):
        code, out, err = self.run_cli(
            ["quest", "add", "demo", "--title", "Demo", "--no-epic", "--tasks", "A,B"],
            "sess-1",
            self.repo_dir,
        )
        self.assertEqual(code, 0, err)
        code, out, err = self.run_cli(["board"], "sess-1", self.repo_dir)
        self.assertIn("queued: A, B", out)

    def test_no_epic_quest_created_with_task_titles(self):
        code, out, err = self.run_cli(
            [
                "quest",
                "add",
                "demo",
                "--title",
                "Demo",
                "--no-epic",
                "--tasks",
                "A,B",
                "--titles",
                "First,Second",
            ],
            "sess-1",
            self.repo_dir,
        )
        self.assertEqual(code, 0, err)
        self.run_cli(["task", "start", "demo/A"], "sess-1", self.repo_dir)
        self.run_cli(["task", "start", "demo/B"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["board"], "sess-1", self.repo_dir)
        self.assertIn("First", out)
        self.assertIn("Second", out)

    def test_titles_length_must_match_tasks(self):
        code, out, err = self.run_cli(
            [
                "quest",
                "add",
                "demo",
                "--title",
                "Demo",
                "--no-epic",
                "--tasks",
                "A,B",
                "--titles",
                "First",
            ],
            "sess-1",
            self.repo_dir,
        )
        self.assertEqual(code, 1)
        self.assertIn("--titles", err)

    def test_titles_require_tasks(self):
        code, out, err = self.run_cli(
            ["quest", "add", "demo", "--title", "Demo", "--no-epic", "--titles", "First"],
            "sess-1",
            self.repo_dir,
        )
        self.assertEqual(code, 1)
        self.assertIn("--titles", err)

    def test_rejects_path_traversal_slug(self):
        code, out, err = self.run_cli(
            ["quest", "add", "../../tmp/x", "--title", "Demo", "--no-epic"], "sess-1", self.repo_dir
        )
        self.assertEqual(code, 1)
        self.assertIn("invalid quest slug", err)

    def test_duplicate_slug_rejected(self):
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(
            ["quest", "add", "demo", "--title", "Demo again", "--no-epic"], "sess-1", self.repo_dir
        )
        self.assertEqual(code, 1)
        self.assertIn("already exists", err)


class QuestFollowupsTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(
            ["party", "start", "alpha", "--reason", "test reason", "--goal", "test goal", "--done-when", "test done"],
            "sess-1",
            self.repo_dir,
        )
        self.run_cli(["quest", "add", "src", "--title", "Source", "--no-epic"], "sess-1", self.repo_dir)

    def test_followups_creates_no_epic_quest_with_tasks(self):
        code, out, err = self.run_cli(
            [
                "quest",
                "add",
                "next",
                "--followups-of",
                "src",
                "--title",
                "Next",
                "--tasks",
                "A,B",
                "--titles",
                "First,Second",
            ],
            "sess-1",
            self.repo_dir,
        )
        self.assertEqual(code, 0, err)
        code, out, err = self.run_cli(["task", "start", "next/A"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        code, out, err = self.run_cli(["board"], "sess-1", self.repo_dir)
        self.assertIn("next", out)
        self.assertIn("First", out)

    def test_followups_without_tasks_allows_task_add(self):
        code, out, err = self.run_cli(
            ["quest", "add", "next", "--followups-of", "src", "--title", "Next"],
            "sess-1",
            self.repo_dir,
        )
        self.assertEqual(code, 0, err)
        code, out, err = self.run_cli(
            ["task", "add", "next/T01", "--title", "One", "--reason", "serves the goal"], "sess-1", self.repo_dir
        )
        self.assertEqual(code, 0, err)

    def test_followups_rejects_unknown_source(self):
        code, out, err = self.run_cli(
            ["quest", "add", "next", "--followups-of", "ghost", "--title", "Next"],
            "sess-1",
            self.repo_dir,
        )
        self.assertEqual(code, 1)
        self.assertIn("unknown quest 'ghost'", err)

    def test_followups_rejects_source_of_other_party(self):
        self.run_cli(
            ["party", "start", "beta", "--reason", "test reason", "--goal", "test goal", "--done-when", "test done"],
            "sess-2",
            self.repo_dir,
        )
        code, out, err = self.run_cli(
            ["quest", "add", "next", "--followups-of", "src", "--title", "Next"],
            "sess-2",
            self.repo_dir,
        )
        self.assertEqual(code, 1)
        self.assertIn("not owned by party 'beta'", err)

    def test_followups_rejects_epic(self):
        code, out, err = self.run_cli(
            ["quest", "add", "next", "--followups-of", "src", "--title", "N", "--epic", "x"],
            "sess-1",
            self.repo_dir,
        )
        self.assertEqual(code, 1)
        self.assertIn("--followups-of cannot be combined", err)

    def test_followups_rejects_no_epic(self):
        code, out, err = self.run_cli(
            ["quest", "add", "next", "--followups-of", "src", "--title", "N", "--no-epic"],
            "sess-1",
            self.repo_dir,
        )
        self.assertEqual(code, 1)
        self.assertIn("--followups-of cannot be combined", err)

    def test_followups_nothing_written_on_rejection(self):
        self.run_cli(
            ["quest", "add", "next", "--followups-of", "ghost", "--title", "N"],
            "sess-1",
            self.repo_dir,
        )
        code, out, err = self.run_cli(["quest", "add", "next", "--title", "N", "--no-epic"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)


class QuestAddConflictTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(
            ["party", "start", "alpha", "--reason", "test reason", "--goal", "test goal", "--done-when", "test done"],
            "sess-1",
            self.repo_dir,
        )
        self.run_cli(
            ["party", "start", "beta", "--reason", "test reason", "--goal", "test goal", "--done-when", "test done"],
            "sess-2",
            self.repo_dir,
        )
        self.sync_sdd(
            self.repo_dir,
            "sess-1",
            "acme",
            "compliance",
            "## T01 — First task\n\n**Deps:** —\n\n**Status:** [ ] pending\n\n"
            "## T02 — Second task\n\n**Deps:** —\n\n**Status:** [ ] pending\n\n"
            "## T03 — Third task\n\n**Deps:** —\n\n**Status:** [ ] pending\n\n"
            "## T05 — Fifth task\n\n**Deps:** —\n\n**Status:** [ ] pending\n",
        )

    def test_conflict_via_other_quest(self):
        self.run_cli(
            ["quest", "add", "alpha-q", "--title", "A", "--epic", "compliance", "--tasks", "T01"],
            "sess-1",
            self.repo_dir,
        )
        code, out, err = self.run_cli(
            ["quest", "add", "beta-q", "--title", "B", "--epic", "compliance", "--tasks", "T01,T03"],
            "sess-2",
            self.repo_dir,
        )
        self.assertEqual(code, 1)
        self.assertIn("T01 is in quest alpha-q of party alpha", err)

    def test_conflict_via_claim(self):
        self.run_cli(["claim", "task:compliance/T02", "--ttl", "8h"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(
            ["quest", "add", "beta-q", "--title", "B", "--epic", "compliance", "--tasks", "T02"],
            "sess-2",
            self.repo_dir,
        )
        self.assertEqual(code, 1)
        self.assertIn("T02 is claimed by party alpha until", err)

    def test_several_conflicts_all_listed(self):
        self.run_cli(
            ["quest", "add", "alpha-q", "--title", "A", "--epic", "compliance", "--tasks", "T01"],
            "sess-1",
            self.repo_dir,
        )
        self.run_cli(["claim", "task:compliance/T05", "--ttl", "8h"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(
            [
                "quest",
                "add",
                "beta-q",
                "--title",
                "B",
                "--epic",
                "compliance",
                "--tasks",
                "T01,T02,T05",
            ],
            "sess-2",
            self.repo_dir,
        )
        self.assertEqual(code, 1)
        self.assertIn("T01 is in quest alpha-q of party alpha", err)
        self.assertIn("T05 is claimed by party alpha until", err)
        self.assertNotIn("T02", err)

    def test_own_quest_allowed(self):
        self.run_cli(
            ["quest", "add", "alpha-q", "--title", "A", "--epic", "compliance", "--tasks", "T01"],
            "sess-1",
            self.repo_dir,
        )
        code, out, err = self.run_cli(
            ["quest", "add", "alpha-q2", "--title", "A2", "--epic", "compliance", "--tasks", "T01"],
            "sess-1",
            self.repo_dir,
        )
        self.assertEqual(code, 0)

    def test_closed_quest_does_not_conflict(self):
        self.run_cli(
            ["quest", "add", "alpha-q", "--title", "A", "--epic", "compliance", "--tasks", "T01"],
            "sess-1",
            self.repo_dir,
        )
        self.run_cli(["quest", "done", "alpha-q", "--force"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(
            ["quest", "add", "beta-q", "--title", "B", "--epic", "compliance", "--tasks", "T01"],
            "sess-2",
            self.repo_dir,
        )
        self.assertEqual(code, 0)

    def test_expired_claim_does_not_conflict(self):
        self.run_cli(["claim", "task:compliance/T01", "--ttl", "30m"], "sess-1", self.repo_dir)
        future = timeutil.utcnow() + timedelta(hours=1)
        with mock.patch("guild.timeutil.utcnow", return_value=future):
            code, out, err = self.run_cli(
                ["quest", "add", "beta-q", "--title", "B", "--epic", "compliance", "--tasks", "T01"],
                "sess-2",
                self.repo_dir,
            )
        self.assertEqual(code, 0)

    def test_other_epic_does_not_conflict(self):
        self.sync_sdd(
            self.repo_dir,
            "sess-1",
            "acme",
            "billing",
            "## T01 — Billing first task\n\n**Deps:** —\n\n**Status:** [ ] pending\n",
        )
        self.run_cli(
            ["quest", "add", "alpha-q", "--title", "A", "--epic", "compliance", "--tasks", "T01"],
            "sess-1",
            self.repo_dir,
        )
        code, out, err = self.run_cli(
            ["quest", "add", "beta-q", "--title", "B", "--epic", "billing", "--tasks", "T01"],
            "sess-2",
            self.repo_dir,
        )
        self.assertEqual(code, 0)

    def test_nothing_written_on_rejection(self):
        self.run_cli(
            ["quest", "add", "alpha-q", "--title", "A", "--epic", "compliance", "--tasks", "T01"],
            "sess-1",
            self.repo_dir,
        )
        code, out, err = self.run_cli(
            ["quest", "add", "beta-q", "--title", "B", "--epic", "compliance", "--tasks", "T01"],
            "sess-2",
            self.repo_dir,
        )
        self.assertEqual(code, 1)
        code, out, err = self.run_cli(["board"], "sess-1", self.repo_dir)
        self.assertNotIn("beta-q", out)


class TaskLifecycleTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(
            ["party", "start", "alpha", "--reason", "test reason", "--goal", "test goal", "--done-when", "test done"],
            "sess-1",
            self.repo_dir,
        )
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", self.repo_dir)

    def test_add_task_to_no_epic_quest(self):
        code, out, err = self.run_cli(
            ["task", "add", "demo/T01", "--title", "First task", "--reason", "serves the goal"], "sess-1", self.repo_dir
        )
        self.assertEqual(code, 0)

    def _add_epic_quest(self):
        self.sync_sdd(
            self.repo_dir,
            "sess-1",
            "acme",
            "compliance",
            "## T09 — Ninth task\n\n**Deps:** —\n\n**Status:** [ ] pending\n",
        )
        self.run_cli(
            ["quest", "add", "epicq", "--title", "E", "--epic", "compliance", "--tasks", "T09"],
            "sess-1",
            self.repo_dir,
        )

    def test_add_task_to_epic_quest_prints_the_sdd_hint(self):
        self._add_epic_quest()
        code, out, err = self.run_cli(
            ["task", "add", "epicq/T10", "--title", "Extra", "--reason", "serves the goal"], "sess-1", self.repo_dir
        )
        self.assertEqual(code, 0, err)
        self.assertIn("task 'epicq/T10' added", out)
        self.assertIn("add T10 to compliance tasks.md in the SDD", out)

    def test_add_task_with_no_sdd_prints_no_hint_and_marks_the_board(self):
        self._add_epic_quest()
        code, out, err = self.run_cli(
            ["task", "add", "epicq/T10", "--title", "Extra", "--no-sdd", "--reason", "serves the goal"],
            "sess-1",
            self.repo_dir,
        )
        self.assertEqual(code, 0, err)
        self.assertNotIn("tasks.md", out)
        code, out, err = self.run_cli(["board"], "sess-1", self.repo_dir)
        self.assertIn("no sdd", out)

    def test_no_sdd_survives_rebuild(self):
        self._add_epic_quest()
        self.run_cli(
            ["task", "add", "epicq/T10", "--title", "Extra", "--no-sdd", "--reason", "serves the goal"],
            "sess-1",
            self.repo_dir,
        )
        self.run_cli(["rebuild"], None, None)
        conn = db.connect(paths.db_path())
        rows = conn.execute("SELECT tid, no_sdd FROM quest_tasks ORDER BY tid").fetchall()
        conn.close()
        self.assertEqual([(row["tid"], row["no_sdd"]) for row in rows], [("T09", 0), ("T10", 1)])

    def test_add_task_to_no_epic_quest_prints_no_hint(self):
        code, out, err = self.run_cli(
            ["task", "add", "demo/T01", "--title", "First task", "--reason", "serves the goal"], "sess-1", self.repo_dir
        )
        self.assertNotIn("tasks.md", out)

    def test_add_task_held_by_another_party_on_an_epic_quest_is_refused(self):
        self.sync_sdd(
            self.repo_dir,
            "sess-1",
            "acme",
            "compliance",
            "## T01 — First task\n\n**Deps:** —\n\n**Status:** [ ] pending\n\n"
            "## T09 — Ninth task\n\n**Deps:** —\n\n**Status:** [ ] pending\n",
        )
        self.run_cli(
            ["quest", "add", "alphaq", "--title", "A", "--epic", "compliance", "--tasks", "T09"],
            "sess-1",
            self.repo_dir,
        )
        self.run_cli(
            ["party", "start", "beta", "--reason", "test reason", "--goal", "test goal", "--done-when", "test done"],
            "sess-2",
            self.repo_dir,
        )
        self.run_cli(
            ["quest", "add", "betaq", "--title", "B", "--epic", "compliance", "--tasks", "T01"],
            "sess-2",
            self.repo_dir,
        )
        code, out, err = self.run_cli(
            ["task", "add", "betaq/T09", "--title", "dup", "--reason", "serves the goal"], "sess-2", self.repo_dir
        )
        self.assertEqual(code, 1)
        self.assertIn("T09 is in quest alphaq of party alpha", err)

    def test_done_on_an_epic_quest_prints_the_sdd_hint(self):
        self._add_epic_quest()
        code, out, err = self.run_cli(["task", "done", "epicq/T09"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        self.assertIn("mark T09 done in compliance tasks.md in the SDD", out)

    def test_done_on_a_free_quest_prints_no_hint(self):
        self.run_cli(
            ["task", "add", "demo/T01", "--title", "First", "--reason", "serves the goal"], "sess-1", self.repo_dir
        )
        code, out, err = self.run_cli(["task", "done", "demo/T01"], "sess-1", self.repo_dir)
        self.assertNotIn("tasks.md", out)

    def test_cannot_add_task_to_done_quest(self):
        self.run_cli(["quest", "done", "demo", "--force"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(
            ["task", "add", "demo/T01", "--title", "First", "--reason", "serves the goal"], "sess-1", self.repo_dir
        )
        self.assertEqual(code, 1)
        self.assertIn("quest 'demo' is done", err)

    def test_start_block_done_cycle(self):
        self.run_cli(
            ["task", "add", "demo/T01", "--title", "First", "--reason", "serves the goal"], "sess-1", self.repo_dir
        )
        code, out, err = self.run_cli(["task", "start", "demo/T01", "--summary", "wip"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0)
        code, out, err = self.run_cli(
            ["task", "block", "demo/T01", "--reason", "waiting on ci"], "sess-1", self.repo_dir
        )
        self.assertEqual(code, 0)
        code, out, err = self.run_cli(["board"], "sess-1", self.repo_dir)
        self.assertIn("blocked: T01 — waiting on ci", out)
        code, out, err = self.run_cli(["task", "done", "demo/T01", "--summary", "shipped"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0)

    def test_block_requires_reason(self):
        self.run_cli(
            ["task", "add", "demo/T01", "--title", "First", "--reason", "serves the goal"], "sess-1", self.repo_dir
        )
        code, out, err = self.run_cli(["task", "block", "demo/T01"], "sess-1", self.repo_dir)
        self.assertEqual(code, 2)

    def test_done_task_cannot_transition_again(self):
        self.run_cli(
            ["task", "add", "demo/T01", "--title", "First", "--reason", "serves the goal"], "sess-1", self.repo_dir
        )
        self.run_cli(["task", "done", "demo/T01"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["task", "start", "demo/T01"], "sess-1", self.repo_dir)
        self.assertEqual(code, 1)
        self.assertIn("already done", err)

    def test_other_party_cannot_mutate_task(self):
        self.run_cli(
            ["task", "add", "demo/T01", "--title", "First", "--reason", "serves the goal"], "sess-1", self.repo_dir
        )
        self.run_cli(
            ["party", "start", "beta", "--reason", "test reason", "--goal", "test goal", "--done-when", "test done"],
            "sess-2",
            self.repo_dir,
        )
        code, out, err = self.run_cli(["task", "start", "demo/T01"], "sess-2", self.repo_dir)
        self.assertEqual(code, 1)
        self.assertIn("owned by party", err)


if __name__ == "__main__":
    import unittest

    unittest.main()
