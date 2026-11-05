from tests.test_task_move import TaskMoveTestCase


class TaskDiscardTestCase(TaskMoveTestCase):
    def _discard(self, ref, extra=(), session="sess-1"):
        return self._cli(session, ["task", "discard", ref, "--reason", "made by mistake"] + list(extra))

    def _refused(self, ref, fragment, extra=()):
        before = self._tasks()
        code, out, err = self._discard(ref, extra)
        self.assertEqual(code, 1, out)
        self.assertIn(fragment, err)
        self.assertEqual(self._tasks(), before)


class TaskDiscardTests(TaskDiscardTestCase):
    def test_discards_a_queued_task_with_reason_author_and_date(self):
        code, out, err = self._discard("src/T01")
        self.assertEqual(code, 0, err)
        self.assertIn("task 'src/T01' discarded", out)
        self.assertIn("remove T01 from wave tasks.md in the SDD", out)
        rows = self._query(
            "SELECT state, discarded_reason, discarded_by, discarded_at IS NOT NULL FROM quest_tasks WHERE tid = 'T01'"
        )
        self.assertEqual(rows, [("discarded", "made by mistake", "alpha", 1)])

    def test_discards_a_blocked_task(self):
        self._cli("sess-1", ["task", "block", "src/T02", "--reason", "waiting"])
        code, out, err = self._discard("src/T02")
        self.assertEqual(code, 0, err)

    def test_reason_is_required(self):
        code, out, err = self._cli("sess-1", ["task", "discard", "src/T01"])
        self.assertEqual(code, 2)

    def test_empty_reason_is_refused(self):
        code, out, err = self._cli("sess-1", ["task", "discard", "src/T01", "--reason", "  "])
        self.assertEqual(code, 1)
        self.assertIn("--reason must not be empty", err)

    def test_done_task_is_refused_even_with_force(self):
        self._cli("sess-1", ["task", "done", "src/T01"])
        self._refused("src/T01", "is done", ["--force"])

    def test_already_discarded_is_refused(self):
        self._discard("src/T01")
        self._refused("src/T01", "already discarded")

    def test_active_task_needs_force(self):
        self._cli("sess-1", ["task", "start", "src/T01"])
        self._refused("src/T01", "is active")
        code, out, err = self._discard("src/T01", ["--force"])
        self.assertEqual(code, 0, err)

    def test_open_pr_needs_force(self):
        self._track_pr("OPEN")
        self._refused("src/T01", "open PR acme/app#1")
        code, out, err = self._discard("src/T01", ["--force"])
        self.assertEqual(code, 0, err)

    def test_live_claim_needs_force(self):
        self._cli("sess-1", ["claim", "task:wave/T01", "--ttl", "30m"])
        self._refused("src/T01", "guild release task:wave/T01")
        code, out, err = self._discard("src/T01", ["--force"])
        self.assertEqual(code, 0, err)

    def test_other_party_cannot_discard(self):
        code, out, err = self._discard("src/T01", session="sess-2")
        self.assertEqual(code, 1)
        self.assertIn("owned by party 'alpha'", err)

    def test_unknown_task(self):
        self._refused("src/T99", "unknown task")

    def test_start_block_and_done_refuse_a_discarded_task(self):
        self._discard("src/T01")
        for action in (["start"], ["block", "--reason", "x"], ["done"]):
            code, out, err = self._cli("sess-1", ["task"] + [action[0], "src/T01"] + action[1:])
            self.assertEqual(code, 1)
            self.assertIn("is discarded", err)

    def test_discarded_task_cannot_move(self):
        self._discard("src/T01")
        code, out, err = self._move("src/T01", "dst")
        self.assertEqual(code, 1)
        self.assertIn("only queued or blocked tasks move", err)


class TaskRestoreTests(TaskDiscardTestCase):
    def test_restore_brings_the_task_back_queued_and_clears_the_discard(self):
        self._discard("src/T01")
        code, out, err = self._cli("sess-1", ["task", "restore", "src/T01"])
        self.assertEqual(code, 0, err)
        self.assertIn("restored as queued", out)
        rows = self._query(
            "SELECT state, discarded_reason, discarded_by, discarded_at FROM quest_tasks WHERE tid = 'T01'"
        )
        self.assertEqual(rows, [("queued", None, None, None)])

    def test_restore_refuses_a_task_that_is_not_discarded(self):
        code, out, err = self._cli("sess-1", ["task", "restore", "src/T01"])
        self.assertEqual(code, 1)
        self.assertIn("is not discarded", err)

    def test_restore_refuses_when_another_party_took_the_tid(self):
        self._discard("src/T01")
        self._cli("sess-2", ["task", "add", "dst/T01", "--title", "Again"])
        code, out, err = self._cli("sess-1", ["task", "restore", "src/T01"])
        self.assertEqual(code, 1)

    def test_rebuild_replays_the_same_state(self):
        self._discard("src/T01")
        self._discard("src/T02")
        self._cli("sess-1", ["task", "restore", "src/T02"])
        before = self._query("SELECT * FROM quest_tasks ORDER BY quest, tid")
        code, out, err = self._cli("sess-1", ["rebuild"])
        self.assertEqual(code, 0, err)
        self.assertEqual(self._query("SELECT * FROM quest_tasks ORDER BY quest, tid"), before)


class DiscardedTaskIgnoredTests(TaskDiscardTestCase):
    def test_quest_done_passes_with_only_done_and_discarded_tasks(self):
        self._discard("src/T03")
        self._discard("src/T02")
        self._cli("sess-1", ["task", "done", "src/T01"])
        code, out, err = self._cli("sess-1", ["quest", "done", "src", "--accept-drift"])
        self.assertEqual(code, 0, err)

    def test_quest_done_still_lists_the_unfinished_tasks_only(self):
        self._discard("src/T03")
        code, out, err = self._cli("sess-1", ["quest", "done", "src"])
        self.assertEqual(code, 1)
        self.assertIn("T01", err)
        self.assertNotIn("T03", err)

    def test_final_report_counts_exclude_discarded(self):
        self._discard("src/T03")
        self._cli("sess-1", ["task", "done", "src/T01"])
        code, out, err = self._cli("sess-1", ["party", "close", "--pending", "none", "--force"])
        self.assertIn("quest src: 1/2 tasks done", out + err)

    def test_brief_shows_a_discarded_lane(self):
        self._discard("src/T03")
        code, out, err = self._cli("sess-1", ["brief"])
        self.assertIn("discarded: T03 — made by mistake", out)
        self.assertNotIn("queued: T01, T02, T03", out)

    def test_board_hides_the_discarded_task(self):
        self._discard("src/T03")
        code, out, err = self._cli("sess-1", ["board"])
        self.assertIn("queued: T01, T02", out)
        self.assertNotIn("T03", out)

    def test_board_counts_the_discarded_tasks(self):
        self._discard("src/T02")
        self._discard("src/T03")
        code, out, err = self._cli("sess-1", ["board"])
        self.assertIn("2 discarded", out)

    def test_board_shows_no_count_without_discarded_tasks(self):
        code, out, err = self._cli("sess-1", ["board"])
        self.assertNotIn("discarded", out)

    def test_release_ignores_a_discarded_task(self):
        self._discard("src/T01")
        self._cli("sess-1", ["task", "move", "src/T02,T03", "--to", "dst"])
        code, out, err = self._cli("sess-1", ["quest", "release", "src"])
        self.assertEqual(code, 0, err)

    def test_discarded_tid_is_free_for_another_party(self):
        self._discard("src/T01")
        code, out, err = self._cli("sess-2", ["task", "add", "dst/T01", "--title", "Again"])
        self.assertEqual(code, 0, err)


class TaskDiscardMetricsTests(TaskDiscardTestCase):
    def test_history_percent_done_excludes_discarded(self):
        self._discard("src/T02")
        self._discard("src/T03")
        self._cli("sess-1", ["task", "done", "src/T01"])
        code, out, err = self._cli("sess-1", ["history"])
        self.assertEqual(code, 0, err)
        self.assertIn("100% (1/1 done)", out)

    def test_incomplete_quest_does_not_list_discarded_tasks(self):
        self._discard("src/T03")
        self._cli("sess-1", ["quest", "done", "src", "--force", "--accept-drift"])
        code, out, err = self._cli("sess-1", ["quest", "incomplete", "src", "--reason", "stopped"])
        self.assertEqual(code, 0, err)
        code, out, err = self._cli("sess-1", ["history"])
        self.assertEqual(code, 0, err)
        self.assertIn("2 of 2 tasks not done when marked", out)

    def test_open_quest_board_skips_discarded_tasks(self):
        self._cli("sess-1", ["quest", "add", "pool", "--title", "Pool", "--no-epic", "--open", "--tasks", "A,B"])
        self._cli("sess-1", ["quest", "take", "pool"])
        self._cli("sess-1", ["task", "discard", "pool/A", "--reason", "mistake"])
        self._cli("sess-1", ["quest", "release", "pool"])
        code, out, err = self._cli("sess-1", ["quest", "board"])
        self.assertIn("B", out)
        self.assertNotIn(" A", out)


if __name__ == "__main__":
    import unittest

    unittest.main()
