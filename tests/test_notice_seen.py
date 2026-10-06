from datetime import timedelta
from unittest import mock

from guild import context, db, paths, timeutil
from guild.commands import board as board_commands
from tests.testutil import GuildTestCase


class NoticeSeenTestCase(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])

    def _create(self, text, ttl):
        code, out, err = self.run_cli(["notice", "create", text, "--to", "guild", "--ttl", ttl], None, None)
        self.assertEqual(code, 0, err)

    def _notices(self):
        code, out, err = self.run_cli(["notices"], None, None)
        self.assertEqual(code, 0, err)
        return out

    def _issued(self, notice_id):
        conn = db.connect(paths.db_path())
        try:
            row = conn.execute("SELECT created_at FROM notices WHERE id = ?", (notice_id,)).fetchone()
        finally:
            conn.close()
        return timeutil.issued_label(row["created_at"])

    def _after(self, delta):
        return mock.patch("guild.timeutil.utcnow", return_value=timeutil.utcnow() + delta)


class SeenCommandTests(NoticeSeenTestCase):
    def test_seen_and_unseen_report_the_notice(self):
        self._create("pipeline down", "5h")
        code, out, err = self.run_cli(["notice", "seen", "1"], None, None)
        self.assertEqual((code, out, err), (0, "notice #1 seen\n", ""))
        code, out, err = self.run_cli(["notice", "unseen", "1"], None, None)
        self.assertEqual((code, out, err), (0, "notice #1 unseen\n", ""))

    def test_bound_session_can_mark_seen_and_unseen(self):
        self.run_cli(["party", "start", "alpha"], "sess-1", self.repo_dir)
        self._create("pipeline down", "5h")
        code, out, err = self.run_cli(["notice", "seen", "1"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        code, out, err = self.run_cli(["notice", "unseen", "1"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)

    def test_unknown_notice(self):
        for action in ("seen", "unseen"):
            with self.subTest(action=action):
                code, out, err = self.run_cli(["notice", action, "99"], None, None)
                self.assertEqual(code, 1)
                self.assertIn("unknown notice #99", err)

    def test_marking_seen_twice_is_an_error(self):
        self._create("pipeline down", "5h")
        self.run_cli(["notice", "seen", "1"], None, None)
        code, out, err = self.run_cli(["notice", "seen", "1"], None, None)
        self.assertEqual(code, 1)
        self.assertIn("notice #1 is already seen", err)

    def test_unseen_on_a_notice_that_is_not_seen_is_an_error(self):
        self._create("pipeline down", "5h")
        code, out, err = self.run_cli(["notice", "unseen", "1"], None, None)
        self.assertEqual(code, 1)
        self.assertIn("notice #1 is not seen", err)

    def test_closed_notice_cannot_be_marked(self):
        self._create("pipeline down", "5h")
        self.run_cli(["notice", "seen", "1"], None, None)
        self.run_cli(["notice", "close", "1"], None, None)
        for action in ("seen", "unseen"):
            with self.subTest(action=action):
                code, out, err = self.run_cli(["notice", action, "1"], None, None)
                self.assertEqual(code, 1)
                self.assertIn("notice #1 is not active", err)

    def test_expired_notice_cannot_be_marked_seen(self):
        self._create("short lived", "30m")
        with self._after(timedelta(hours=1)):
            code, out, err = self.run_cli(["notice", "seen", "1"], None, None)
        self.assertEqual(code, 1)
        self.assertIn("notice #1 is not active", err)

    def test_records_events_and_keeps_the_notice_active(self):
        self._create("pipeline down", "5h")
        self.run_cli(["notice", "seen", "1"], None, None)
        conn = db.connect(paths.db_path())
        row = conn.execute("SELECT state, seen_at FROM notices WHERE id = 1").fetchone()
        self.assertEqual(row["state"], "active")
        self.assertIsNotNone(row["seen_at"])
        self.run_cli(["notice", "unseen", "1"], None, None)
        row = conn.execute("SELECT state, seen_at FROM notices WHERE id = 1").fetchone()
        self.assertEqual((row["state"], row["seen_at"]), ("active", None))
        kinds = [r["kind"] for r in conn.execute("SELECT kind FROM events ORDER BY seq").fetchall()]
        self.assertEqual(kinds, ["notice.created", "notice.seen", "notice.unseen"])


class SeenAllTests(NoticeSeenTestCase):
    def test_all_marks_every_unseen_active_notice(self):
        self._create("pipeline down", "5h")
        self._create("ci flaky", "2h")
        self._create("already read", "2h")
        self.run_cli(["notice", "seen", "3"], None, None)
        code, out, err = self.run_cli(["notice", "seen", "--all"], None, None)
        self.assertEqual((code, out, err), (0, "2 notices marked seen\n", ""))
        self.assertNotIn("new", self._notices())

    def test_all_with_nothing_unseen_reports_zero(self):
        self._create("pipeline down", "5h")
        self.run_cli(["notice", "seen", "1"], None, None)
        code, out, err = self.run_cli(["notice", "seen", "--all"], None, None)
        self.assertEqual((code, out, err), (0, "0 notices marked seen\n", ""))

    def test_all_skips_closed_and_expired_notices(self):
        self._create("closed one", "5h")
        self._create("live one", "5h")
        self.run_cli(["notice", "close", "1"], None, None)
        code, out, err = self.run_cli(["notice", "seen", "--all"], None, None)
        self.assertEqual(out, "1 notices marked seen\n")

    def test_id_and_all_are_mutually_exclusive(self):
        self._create("pipeline down", "5h")
        code, out, err = self.run_cli(["notice", "seen", "1", "--all"], None, None)
        self.assertEqual(code, 2)
        self.assertIn("not allowed with", err)

    def test_one_of_id_or_all_is_required(self):
        code, out, err = self.run_cli(["notice", "seen"], None, None)
        self.assertEqual(code, 2)
        self.assertIn("required", err)

    def test_unseen_takes_no_all_flag(self):
        code, out, err = self.run_cli(["notice", "unseen", "--all"], None, None)
        self.assertEqual(code, 2)


class SeenListTests(NoticeSeenTestCase):
    def test_unseen_notices_are_prefixed_new_and_counted(self):
        self._create("pipeline down", "5h")
        self._create("ci flaky", "2h")
        out = self._notices().splitlines()
        self.assertEqual(out[0], "new #2 [human] ci flaky (guild, {}, 1h left)".format(self._issued(2)))
        self.assertEqual(out[1], "new #1 [human] pipeline down (guild, {}, 4h left)".format(self._issued(1)))
        self.assertEqual(out[2], "2 new")

    def test_seen_notice_stays_listed_without_the_marker(self):
        self._create("pipeline down", "5h")
        self._create("ci flaky", "2h")
        self.run_cli(["notice", "seen", "1"], None, None)
        out = self._notices().splitlines()
        self.assertEqual(out[0], "new #2 [human] ci flaky (guild, {}, 1h left)".format(self._issued(2)))
        self.assertEqual(out[1], "#1 [human] pipeline down (guild, {}, 4h left)".format(self._issued(1)))
        self.assertEqual(out[2], "1 new")

    def test_no_count_line_when_everything_is_seen(self):
        self._create("pipeline down", "5h")
        self.run_cli(["notice", "seen", "1"], None, None)
        self.assertEqual(
            self._notices(), "#1 [human] pipeline down (guild, {}, 4h left)\n".format(self._issued(1))
        )

    def test_unseen_restores_the_marker(self):
        self._create("pipeline down", "5h")
        self.run_cli(["notice", "seen", "1"], None, None)
        self.run_cli(["notice", "unseen", "1"], None, None)
        self.assertTrue(self._notices().startswith("new #1"))

    def test_empty_list_prints_nothing(self):
        self.assertEqual(self._notices(), "")

    def test_expired_notice_leaves_the_list(self):
        self._create("short lived", "30m")
        with self._after(timedelta(hours=1)):
            self.assertEqual(self._notices(), "")


class SeenBoardTests(NoticeSeenTestCase):
    def _board(self, *extra):
        code, out, err = self.run_cli(["board"] + list(extra), None, None)
        self.assertEqual(code, 0, err)
        return out

    def _colored_board(self):
        conn = db.connect(paths.db_path())
        ctx = context.RunContext(
            conn, None, None, timeutil.utcnow(), None,
            paths.claude_sessions_dir(), paths.projects_config_dir(), paths.state_dir(),
        )
        try:
            return "\n".join(board_commands.render_board(ctx, None, None, True, 80))
        finally:
            conn.close()

    def test_board_shows_every_notice_with_new_marker_and_counts(self):
        self._create("pipeline down", "5h")
        self._create("ci flaky", "2h")
        self.run_cli(["notice", "seen", "1"], None, None)
        out = self._board()
        self.assertIn("NOTICES · 2 active (1 new)", out)
        self.assertIn("  #1 human · {} · guild · 4h left".format(self._issued(1)), out)
        self.assertIn("  new #2 human · {} · guild · 1h left".format(self._issued(2)), out)
        self.assertIn("pipeline down", out)
        self.assertIn("ci flaky", out)

    def test_board_header_has_no_new_count_when_all_seen(self):
        self._create("pipeline down", "5h")
        self.run_cli(["notice", "seen", "1"], None, None)
        out = self._board()
        self.assertIn("NOTICES · 1 active\n", out)
        self.assertNotIn("new", out)

    def test_party_board_counts_only_that_partys_notices(self):
        self.run_cli(["party", "start", "alpha"], "sess-1", self.repo_dir)
        self.run_cli(["notice", "create", "mine", "--to", "guild", "--ttl", "2h"], "sess-1", self.repo_dir)
        self._create("theirs", "2h")
        out = self._board("--party", "alpha")
        self.assertIn("NOTICES · 1 active (1 new)", out)

    def test_marker_is_colored_on_a_tty_and_plain_otherwise(self):
        self._create("pipeline down", "5h")
        self.assertIn("\033[32mnew\033[0m", self._colored_board())
        self.assertNotIn("\033", self._board())


class SeenNeverChangesDeliveryTests(NoticeSeenTestCase):
    def setUp(self):
        super().setUp()
        self.run_cli(["party", "start", "beta"], "sess-2", self.repo_dir)
        self._create("pipeline down", "5h")
        self.run_cli(["notice", "seen", "1"], None, None)
        self.payload = {"session_id": "sess-2", "cwd": str(self.repo_dir)}

    def test_inbox_still_delivers_a_seen_notice(self):
        code, out, err = self.run_cli(["inbox", "--since-last"], "sess-2", self.repo_dir)
        self.assertIn('- notice #1 from human at {}: "pipeline down"'.format(self._issued(1)), out)

    def test_prompt_submit_still_delivers_a_seen_notice(self):
        code, out, err = self.run_hook("prompt-submit", self.payload)
        self.assertIn("pipeline down", out)

    def test_post_tool_use_still_delivers_a_seen_notice(self):
        code, out, err = self.run_hook("post-tool-use", self.payload)
        self.assertIn("pipeline down", out)

    def test_session_start_brief_still_lists_a_seen_notice(self):
        code, out, err = self.run_hook("session-start", self.payload)
        self.assertIn("pipeline down", out)

    def test_brief_command_still_lists_a_seen_notice(self):
        code, out, err = self.run_cli(["brief"], "sess-2", self.repo_dir)
        self.assertIn("pipeline down", out)

    def test_seen_events_add_no_inbox_lines(self):
        self.run_cli(["inbox", "--since-last"], "sess-2", self.repo_dir)
        self.run_cli(["notice", "unseen", "1"], None, None)
        self.run_cli(["notice", "seen", "--all"], None, None)
        code, out, err = self.run_cli(["inbox", "--since-last"], "sess-2", self.repo_dir)
        self.assertEqual(out, "")

    def test_delivery_is_identical_before_and_after_marking(self):
        self.run_cli(["notice", "unseen", "1"], None, None)
        code, before, err = self.run_cli(["brief"], "sess-2", self.repo_dir)
        self.run_cli(["notice", "seen", "1"], None, None)
        code, after, err = self.run_cli(["brief"], "sess-2", self.repo_dir)
        self.assertEqual(before, after)


if __name__ == "__main__":
    import unittest

    unittest.main()
