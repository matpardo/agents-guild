import sqlite3

from tests.testutil import GuildTestCase

_PAUSE_TEXT = "raid ci paused: finish current step and leave guild handoff"


class RaidPauseTestCase(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha"], "sess-1", self.repo_dir)
        self.run_cli(["party", "start", "beta"], "sess-2", self.repo_dir)
        self.run_cli(["raid", "join", "ci", "--ttl", "8h", "--lead"], "sess-1", self.repo_dir)
        self.run_cli(["raid", "join", "ci", "--ttl", "8h"], "sess-2", self.repo_dir)

    def _pause_row(self, raid_name):
        conn = sqlite3.connect(str(self.data_home / "guild" / "guild.db"))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM raid_pauses WHERE raid = ?", (raid_name,)).fetchone()
        conn.close()
        return row

    def _prompt(self, session_id):
        return self.run_hook("prompt-submit", {"session_id": session_id, "cwd": str(self.repo_dir)})

    def _post_tool(self, session_id):
        return self.run_hook(
            "post-tool-use",
            {"session_id": session_id, "cwd": str(self.repo_dir), "tool_name": "Bash", "tool_input": {}},
        )


class PauseResumeCommandTests(RaidPauseTestCase):
    def test_lead_pauses_and_state_is_stored(self):
        code, out, err = self.run_cli(["raid", "pause", "ci"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        self.assertIn("raid 'ci' paused", out)
        self.assertEqual(self._pause_row("ci")["paused_by"], "alpha")

    def test_non_lead_member_cannot_pause_when_lead_exists(self):
        code, out, err = self.run_cli(["raid", "pause", "ci"], "sess-2", self.repo_dir)
        self.assertEqual(code, 1)
        self.assertIn("only the raid lead 'alpha'", err)
        self.assertIsNone(self._pause_row("ci"))

    def test_any_member_may_pause_when_no_lead(self):
        self.run_cli(["raid", "leave", "ci"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["raid", "pause", "ci"], "sess-2", self.repo_dir)
        self.assertEqual(code, 0, err)

    def test_non_member_cannot_pause(self):
        self.run_cli(["party", "start", "gamma"], "sess-3", self.repo_dir)
        code, out, err = self.run_cli(["raid", "pause", "ci"], "sess-3", self.repo_dir)
        self.assertEqual(code, 1)
        self.assertIn("not a member of raid 'ci'", err)

    def test_pause_requires_binding_for_a_session(self):
        code, out, err = self.run_cli(["raid", "pause", "ci"], "sess-9", self.repo_dir)
        self.assertEqual(code, 1)
        self.assertIn("session not bound", err)

    def test_human_pauses_without_a_session(self):
        code, out, err = self.run_cli(["raid", "pause", "ci"], None, None)
        self.assertEqual(code, 0, err)
        self.assertEqual(self._pause_row("ci")["paused_by"], "human")

    def test_pause_twice_fails(self):
        self.run_cli(["raid", "pause", "ci"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["raid", "pause", "ci"], "sess-1", self.repo_dir)
        self.assertEqual(code, 1)
        self.assertIn("raid 'ci' is already paused", err)

    def test_resume_clears_state_and_posts_raid_notice(self):
        self.run_cli(["raid", "pause", "ci"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["raid", "resume", "ci"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        self.assertIn("raid 'ci' resumed", out)
        self.assertIsNone(self._pause_row("ci"))
        code, out, err = self.run_cli(["inbox", "--since-last"], "sess-2", self.repo_dir)
        self.assertIn("raid ci resumed", out)

    def test_resume_by_non_lead_fails(self):
        self.run_cli(["raid", "pause", "ci"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["raid", "resume", "ci"], "sess-2", self.repo_dir)
        self.assertEqual(code, 1)
        self.assertIn("only the raid lead 'alpha'", err)
        self.assertIsNotNone(self._pause_row("ci"))

    def test_resume_when_not_paused_fails(self):
        code, out, err = self.run_cli(["raid", "resume", "ci"], "sess-1", self.repo_dir)
        self.assertEqual(code, 1)
        self.assertIn("raid 'ci' is not paused", err)

    def test_rebuild_reproduces_pause(self):
        self.run_cli(["raid", "pause", "ci"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["rebuild"], None, None)
        self.assertEqual(code, 0, err)
        self.assertEqual(self._pause_row("ci")["paused_by"], "alpha")

    def test_rebuild_reproduces_resume(self):
        self.run_cli(["raid", "pause", "ci"], "sess-1", self.repo_dir)
        self.run_cli(["raid", "resume", "ci"], "sess-1", self.repo_dir)
        self.run_cli(["rebuild"], None, None)
        self.assertIsNone(self._pause_row("ci"))


class PauseVisibilityTests(RaidPauseTestCase):
    def test_raids_lists_paused_marker(self):
        self.run_cli(["raid", "pause", "ci"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["raids"], None, None)
        self.assertIn("ci (paused):", out)

    def test_raids_has_no_marker_when_running(self):
        code, out, err = self.run_cli(["raids"], None, None)
        self.assertNotIn("paused", out)

    def test_board_shows_paused_raid_for_party(self):
        self.run_cli(["raid", "pause", "ci"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["board"], None, None)
        self.assertIn("raids: ci (PAUSED, lead,", out)

    def test_raid_board_header_shows_pause(self):
        self.run_cli(["raid", "pause", "ci"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["board", "--raid", "ci"], None, None)
        self.assertIn("raid ci PAUSED", out)


class PauseNextTests(RaidPauseTestCase):
    def _queue_task(self, session_id, quest):
        self.run_cli(["quest", "add", quest, "--title", "Demo", "--no-epic"], session_id, self.repo_dir)
        self.run_cli(["task", "add", "{}/T01".format(quest), "--title", "First"], session_id, self.repo_dir)

    def test_next_reports_raid_paused_for_member(self):
        self._queue_task("sess-2", "demo")
        self.run_cli(["raid", "pause", "ci"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["next"], "sess-2", self.repo_dir)
        self.assertEqual(code, 0, err)
        self.assertIn("nothing actionable", out)
        self.assertIn("raid paused: ci", out)
        self.assertNotIn("T01", out)

    def test_next_all_reports_raid_paused(self):
        self.run_cli(["raid", "pause", "ci"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["next", "--all"], "sess-2", self.repo_dir)
        self.assertIn("raid paused: ci", out)

    def test_next_works_again_after_resume(self):
        self._queue_task("sess-2", "demo")
        self.run_cli(["raid", "pause", "ci"], "sess-1", self.repo_dir)
        self.run_cli(["raid", "resume", "ci"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["next"], "sess-2", self.repo_dir)
        self.assertIn("T01", out)

    def test_next_unaffected_for_party_outside_raid(self):
        self.run_cli(["party", "start", "gamma"], "sess-3", self.repo_dir)
        self._queue_task("sess-3", "solo")
        self.run_cli(["raid", "pause", "ci"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["next"], "sess-3", self.repo_dir)
        self.assertIn("T01", out)


class PauseHookTests(RaidPauseTestCase):
    def test_prompt_submit_injects_pause_text_once_per_pause(self):
        self.run_cli(["raid", "pause", "ci"], "sess-1", self.repo_dir)
        code, out, err = self._prompt("sess-2")
        self.assertIn(_PAUSE_TEXT, out)
        code, out, err = self._prompt("sess-2")
        self.assertNotIn(_PAUSE_TEXT, out)

    def test_post_tool_use_injects_pause_text_once(self):
        self.run_cli(["raid", "pause", "ci"], "sess-1", self.repo_dir)
        code, out, err = self._post_tool("sess-2")
        self.assertIn(_PAUSE_TEXT, out)
        code, out, err = self._post_tool("sess-2")
        self.assertNotIn(_PAUSE_TEXT, out)

    def test_marker_shared_between_hooks(self):
        self.run_cli(["raid", "pause", "ci"], "sess-1", self.repo_dir)
        self._prompt("sess-2")
        code, out, err = self._post_tool("sess-2")
        self.assertNotIn(_PAUSE_TEXT, out)

    def test_each_session_gets_its_own_injection(self):
        self.run_cli(["raid", "pause", "ci"], "sess-1", self.repo_dir)
        self._prompt("sess-2")
        code, out, err = self._prompt("sess-1")
        self.assertIn(_PAUSE_TEXT, out)

    def test_second_pause_injects_again(self):
        self.run_cli(["raid", "pause", "ci"], "sess-1", self.repo_dir)
        self._prompt("sess-2")
        self.run_cli(["raid", "resume", "ci"], "sess-1", self.repo_dir)
        self.run_cli(["raid", "pause", "ci"], "sess-1", self.repo_dir)
        code, out, err = self._prompt("sess-2")
        self.assertIn(_PAUSE_TEXT, out)

    def test_no_injection_when_not_paused(self):
        code, out, err = self._prompt("sess-2")
        self.assertNotIn("paused", out)

    def test_no_injection_for_unbound_session(self):
        self.run_cli(["raid", "pause", "ci"], "sess-1", self.repo_dir)
        code, out, err = self._prompt("sess-9")
        self.assertNotIn(_PAUSE_TEXT, out)

    def test_no_injection_after_resume(self):
        self.run_cli(["raid", "pause", "ci"], "sess-1", self.repo_dir)
        self.run_cli(["raid", "resume", "ci"], "sess-1", self.repo_dir)
        code, out, err = self._prompt("sess-2")
        self.assertNotIn(_PAUSE_TEXT, out)


if __name__ == "__main__":
    import unittest

    unittest.main()
