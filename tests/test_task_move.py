import sqlite3

from tests.testutil import GuildTestCase

_TASKS_MD = (
    "## T01 — First\n\n**Deps:** —\n\n**Status:** [ ] pending\n\n"
    "## T02 — Second\n\n**Deps:** —\n\n**Status:** [ ] pending\n\n"
    "## T03 — Third\n\n**Deps:** —\n\n**Status:** [ ] pending\n"
)


class TaskMoveTestCase(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.sync_sdd(self.repo_dir, "sess-1", "acme", "wave", _TASKS_MD)
        self.run_cli(["party", "start", "alpha", "--reason", "test reason"], "sess-1", self.repo_dir)
        self.run_cli(["party", "start", "beta", "--reason", "test reason"], "sess-2", self.repo_dir)
        self._cli(
            "sess-1", ["quest", "add", "src", "--title", "Src", "--epic", "wave", "--tasks", "T01,T02,T03"]
        )
        self._cli("sess-2", ["quest", "add", "dst", "--title", "Dst", "--epic", "wave"])

    def _cli(self, session, argv):
        return self.run_cli(argv, session, self.repo_dir)

    def _move(self, ref, target, session="sess-1"):
        return self._cli(session, ["task", "move", ref, "--to", target])

    def _query(self, sql):
        conn = sqlite3.connect(str(self.data_home / "guild" / "guild.db"))
        conn.row_factory = sqlite3.Row
        try:
            return [tuple(row) for row in conn.execute(sql).fetchall()]
        finally:
            conn.close()

    def _track_pr(self, gh_state):
        self.write_gh_fixture(
            "view_acme-app_1",
            {
                "state": gh_state, "isDraft": False, "headRefName": "feature/x", "title": "t",
                "mergedAt": "2026-01-01T00:00:00Z", "statusCheckRollup": [],
            },
        )
        code, out, err = self._cli(
            "sess-1", ["pr", "track", "acme/app#1", "--task", "src/T01", "--what", "x", "--waits", "y"]
        )
        self.assertEqual(code, 0, err)

    def _tasks(self):
        return self._query("SELECT quest, tid, state, blocked_reason FROM quest_tasks ORDER BY quest, tid")


class TaskMoveTests(TaskMoveTestCase):
    def test_moves_queued_and_blocked_tasks_keeping_state(self):
        self._cli("sess-1", ["task", "block", "src/T02", "--reason", "waiting"])
        code, out, err = self._move("src/T01,T02", "dst")
        self.assertEqual(code, 0, err)
        self.assertIn("task 'src/T01' moved to 'dst' (party beta)", out)
        self.assertEqual(
            self._tasks(),
            [
                ("dst", "T01", "queued", None),
                ("dst", "T02", "blocked", "waiting"),
                ("src", "T03", "queued", None),
            ],
        )

    def test_target_party_can_start_the_moved_task(self):
        self._move("src/T01", "dst")
        code, out, err = self._cli("sess-2", ["task", "start", "dst/T01"])
        self.assertEqual(code, 0, err)
        code, out, err = self._cli("sess-1", ["task", "start", "src/T01"])
        self.assertEqual(code, 1)

    def test_source_quest_done_no_longer_counts_moved_tasks(self):
        self._move("src/T01,T02", "dst")
        self._cli("sess-1", ["task", "done", "src/T03"])
        code, out, err = self._cli("sess-1", ["quest", "done", "src", "--accept-drift"])
        self.assertEqual(code, 0, err)

    def test_pr_is_repointed_to_the_target_quest(self):
        self._track_pr("MERGED")
        self._cli("sess-1", ["sync", "--source", "gh"])
        code, out, err = self._move("src/T01", "dst")
        self.assertEqual(code, 0, err)
        self.assertEqual(self._query("SELECT task_quest, task_tid FROM prs"), [("dst", "T01")])

    def test_rebuild_reproduces_the_move(self):
        self._move("src/T01", "dst")
        before = self._tasks()
        self.run_cli(["rebuild"], None, None)
        self.assertEqual(self._tasks(), before)


class TaskMoveRefusalTests(TaskMoveTestCase):
    def _refused(self, ref, target, session, text):
        code, out, err = self._move(ref, target, session)
        self.assertEqual(code, 1)
        self.assertIn(text, err)
        return self._tasks()

    def test_only_the_source_owner_moves(self):
        self._refused("src/T01", "dst", "sess-2", "owned by party 'alpha'")

    def test_unknown_target(self):
        self._refused("src/T01", "ghost", "sess-1", "unknown quest 'ghost'")

    def test_target_equals_source(self):
        self._refused("src/T01", "src", "sess-1", "source quest")

    def test_done_target(self):
        self._cli("sess-2", ["quest", "done", "dst"])
        self._refused("src/T01", "dst", "sess-1", "quest 'dst' is done")

    def test_epic_mismatch(self):
        self._cli("sess-2", ["quest", "add", "free", "--title", "Free", "--no-epic"])
        self._refused("src/T01", "free", "sess-1", "another epic")

    def test_project_mismatch(self):
        other_repo = self.register_project("other", ["other/app"])
        self.run_cli(["party", "start", "gamma", "--reason", "test reason"], "sess-3", other_repo)
        self.run_cli(["quest", "add", "far", "--title", "Far", "--no-epic"], "sess-3", other_repo)
        self._cli("sess-1", ["quest", "add", "near", "--title", "Near", "--no-epic"])
        self._cli("sess-1", ["task", "add", "near/N1", "--title", "N"])
        self._refused("near/N1", "far", "sess-1", "another project")

    def test_active_task(self):
        self._cli("sess-1", ["task", "start", "src/T01"])
        self._refused("src/T01", "dst", "sess-1", "only queued or blocked")

    def test_done_task(self):
        self._cli("sess-1", ["task", "done", "src/T01"])
        self._refused("src/T01", "dst", "sess-1", "only queued or blocked")

    def test_unknown_task(self):
        self._refused("src/T99", "dst", "sess-1", "unknown task")

    def test_tid_already_in_target(self):
        self._cli("sess-1", ["quest", "add", "free-a", "--title", "A", "--no-epic", "--tasks", "X"])
        self._cli("sess-2", ["quest", "add", "free-b", "--title", "B", "--no-epic", "--tasks", "X"])
        self._refused("free-a/X", "free-b", "sess-1", "already exists")

    def test_open_pr(self):
        self._track_pr("OPEN")
        self._refused("src/T01", "dst", "sess-1", "open PR acme/app#1")

    def test_live_claim(self):
        self._cli("sess-1", ["claim", "task:wave/T01", "--ttl", "30m"])
        self._refused("src/T01", "dst", "sess-1", "guild release task:wave/T01")

    def test_nothing_moves_when_one_task_is_refused(self):
        self._cli("sess-1", ["task", "start", "src/T02"])
        before = self._tasks()
        self.assertEqual(self._refused("src/T01,T02", "dst", "sess-1", "T02"), before)

    def test_duplicate_tid_in_list(self):
        self._refused("src/T01,T01", "dst", "sess-1", "duplicate")
