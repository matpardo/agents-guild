from datetime import timedelta
from unittest import mock

from guild import db, paths, timeutil
from tests.testutil import GuildTestCase


class NoticeArchiveTestCase(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])

    def _create(self, text, ttl):
        code, out, err = self.run_cli(["notice", "create", text, "--to", "guild", "--ttl", ttl], None, None)
        self.assertEqual(code, 0, err)

    def _notices(self, *extra):
        code, out, err = self.run_cli(["notices"] + list(extra), None, None)
        self.assertEqual(code, 0, err)
        return out

    def _after(self, delta):
        return mock.patch("guild.timeutil.utcnow", return_value=timeutil.utcnow() + delta)


class ArchiveCommandTests(NoticeArchiveTestCase):
    def test_archive_and_unarchive_report_the_notice(self):
        self._create("pipeline down", "5h")
        code, out, err = self.run_cli(["notice", "archive", "1"], None, None)
        self.assertEqual((code, out, err), (0, "notice #1 archived\n", ""))
        code, out, err = self.run_cli(["notice", "unarchive", "1"], None, None)
        self.assertEqual((code, out, err), (0, "notice #1 unarchived\n", ""))

    def test_bound_session_can_archive_and_unarchive(self):
        self.run_cli(["party", "start", "alpha"], "sess-1", self.repo_dir)
        self._create("pipeline down", "5h")
        code, out, err = self.run_cli(["notice", "archive", "1"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        code, out, err = self.run_cli(["notice", "unarchive", "1"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)

    def test_unknown_notice(self):
        for action in ("archive", "unarchive"):
            with self.subTest(action=action):
                code, out, err = self.run_cli(["notice", action, "99"], None, None)
                self.assertEqual(code, 1)
                self.assertIn("unknown notice #99", err)

    def test_archiving_twice_is_an_error(self):
        self._create("pipeline down", "5h")
        self.run_cli(["notice", "archive", "1"], None, None)
        code, out, err = self.run_cli(["notice", "archive", "1"], None, None)
        self.assertEqual(code, 1)
        self.assertIn("notice #1 is already archived", err)

    def test_unarchiving_a_notice_that_is_not_archived_is_an_error(self):
        self._create("pipeline down", "5h")
        code, out, err = self.run_cli(["notice", "unarchive", "1"], None, None)
        self.assertEqual(code, 1)
        self.assertIn("notice #1 is not archived", err)

    def test_closed_notice_cannot_be_archived_or_unarchived(self):
        self._create("pipeline down", "5h")
        self.run_cli(["notice", "archive", "1"], None, None)
        self.run_cli(["notice", "close", "1"], None, None)
        for action in ("archive", "unarchive"):
            with self.subTest(action=action):
                code, out, err = self.run_cli(["notice", action, "1"], None, None)
                self.assertEqual(code, 1)
                self.assertIn("notice #1 is not active", err)

    def test_expired_notice_cannot_be_archived(self):
        self._create("short lived", "30m")
        with self._after(timedelta(hours=1)):
            code, out, err = self.run_cli(["notice", "archive", "1"], None, None)
        self.assertEqual(code, 1)
        self.assertIn("notice #1 is not active", err)

    def test_archiving_records_events_and_keeps_the_notice_active(self):
        self._create("pipeline down", "5h")
        self.run_cli(["notice", "archive", "1"], None, None)
        conn = db.connect(paths.db_path())
        row = conn.execute("SELECT state, archived_at FROM notices WHERE id = 1").fetchone()
        self.assertEqual(row["state"], "active")
        self.assertIsNotNone(row["archived_at"])
        self.run_cli(["notice", "unarchive", "1"], None, None)
        row = conn.execute("SELECT state, archived_at FROM notices WHERE id = 1").fetchone()
        self.assertEqual((row["state"], row["archived_at"]), ("active", None))
        kinds = [r["kind"] for r in conn.execute("SELECT kind FROM events ORDER BY seq").fetchall()]
        self.assertEqual(kinds, ["notice.created", "notice.archived", "notice.unarchived"])


class ArchiveListTests(NoticeArchiveTestCase):
    def test_notices_show_time_left(self):
        self._create("pipeline down", "5h")
        self.assertIn("pipeline down (guild, 4h left)", self._notices())

    def test_notices_hide_archived_and_show_the_hint(self):
        self._create("pipeline down", "5h")
        self._create("ci flaky", "2h")
        self.run_cli(["notice", "archive", "1"], None, None)
        out = self._notices()
        self.assertNotIn("pipeline down", out)
        self.assertIn("ci flaky", out)
        self.assertEqual(out.splitlines()[-1], "1 archived (guild notices --archived)")

    def test_hint_shown_when_everything_is_archived(self):
        self._create("pipeline down", "5h")
        self.run_cli(["notice", "archive", "1"], None, None)
        self.assertEqual(self._notices(), "1 archived (guild notices --archived)\n")

    def test_no_hint_without_archived_notices(self):
        self._create("pipeline down", "5h")
        self.assertNotIn("archived", self._notices())

    def test_archived_flag_lists_only_archived_with_time_left(self):
        self._create("pipeline down", "5h")
        self._create("ci flaky", "2h")
        self.run_cli(["notice", "archive", "1"], None, None)
        out = self._notices("--archived")
        self.assertIn("pipeline down (guild, 4h left)", out)
        self.assertNotIn("ci flaky", out)
        self.assertNotIn("archived (guild", out)

    def test_unarchive_restores_the_notice(self):
        self._create("pipeline down", "5h")
        self.run_cli(["notice", "archive", "1"], None, None)
        self.run_cli(["notice", "unarchive", "1"], None, None)
        self.assertIn("pipeline down", self._notices())
        self.assertEqual(self._notices("--archived"), "")

    def test_expiry_removes_a_notice_from_both_lists(self):
        self._create("short lived", "30m")
        self._create("archived short", "30m")
        self.run_cli(["notice", "archive", "2"], None, None)
        with self._after(timedelta(hours=1)):
            self.assertEqual(self._notices(), "")
            self.assertEqual(self._notices("--archived"), "")

    def test_closed_archived_notice_leaves_the_archived_list(self):
        self._create("pipeline down", "5h")
        self.run_cli(["notice", "archive", "1"], None, None)
        self.run_cli(["notice", "close", "1"], None, None)
        self.assertEqual(self._notices("--archived"), "")
        self.assertEqual(self._notices(), "")


class ArchiveBoardTests(NoticeArchiveTestCase):
    def _board(self, *extra):
        code, out, err = self.run_cli(["board"] + list(extra), None, None)
        self.assertEqual(code, 0, err)
        return out

    def test_board_excludes_archived_and_shows_the_hint(self):
        self._create("pipeline down", "5h")
        self._create("ci flaky", "2h")
        self.run_cli(["notice", "archive", "1"], None, None)
        out = self._board()
        self.assertIn("NOTICES · 1 active", out)
        self.assertNotIn("pipeline down", out)
        self.assertIn("ci flaky", out)
        self.assertIn("1 archived (guild notices --archived)", out)

    def test_board_without_archived_has_no_hint(self):
        self._create("pipeline down", "5h")
        self.assertNotIn("archived", self._board())

    def test_board_with_only_archived_notices_shows_hint(self):
        self._create("pipeline down", "5h")
        self.run_cli(["notice", "archive", "1"], None, None)
        out = self._board()
        self.assertIn("NOTICES · 0 active", out)
        self.assertIn("1 archived (guild notices --archived)", out)

    def test_party_board_counts_only_that_partys_archived_notices(self):
        self.run_cli(["party", "start", "alpha"], "sess-1", self.repo_dir)
        self.run_cli(["notice", "create", "mine", "--to", "guild", "--ttl", "2h"], "sess-1", self.repo_dir)
        self._create("theirs", "2h")
        self.run_cli(["notice", "archive", "1"], None, None)
        self.run_cli(["notice", "archive", "2"], None, None)
        out = self._board("--party", "alpha")
        self.assertIn("1 archived (guild notices --archived)", out)


class ArchiveNeverChangesDeliveryTests(NoticeArchiveTestCase):
    def setUp(self):
        super().setUp()
        self.run_cli(["party", "start", "beta"], "sess-2", self.repo_dir)
        self._create("pipeline down", "5h")
        self.run_cli(["notice", "archive", "1"], None, None)
        self.payload = {"session_id": "sess-2", "cwd": str(self.repo_dir)}

    def test_inbox_still_delivers_an_archived_notice(self):
        code, out, err = self.run_cli(["inbox", "--since-last"], "sess-2", self.repo_dir)
        self.assertIn('- notice #1 from human: "pipeline down"', out)

    def test_prompt_submit_still_delivers_an_archived_notice(self):
        code, out, err = self.run_hook("prompt-submit", self.payload)
        self.assertIn("pipeline down", out)

    def test_post_tool_use_still_delivers_an_archived_notice(self):
        code, out, err = self.run_hook("post-tool-use", self.payload)
        self.assertIn("pipeline down", out)

    def test_session_start_brief_still_lists_an_archived_notice(self):
        code, out, err = self.run_hook("session-start", self.payload)
        self.assertIn("pipeline down", out)

    def test_brief_command_still_lists_an_archived_notice(self):
        code, out, err = self.run_cli(["brief"], "sess-2", self.repo_dir)
        self.assertIn("pipeline down", out)

    def test_archive_events_add_no_inbox_lines(self):
        self.run_cli(["inbox", "--since-last"], "sess-2", self.repo_dir)
        self.run_cli(["notice", "unarchive", "1"], None, None)
        self.run_cli(["notice", "archive", "1"], None, None)
        code, out, err = self.run_cli(["inbox", "--since-last"], "sess-2", self.repo_dir)
        self.assertEqual(out, "")

    def test_delivery_is_identical_with_and_without_archiving(self):
        self.run_cli(["notice", "unarchive", "1"], None, None)
        code, before, err = self.run_cli(["brief"], "sess-2", self.repo_dir)
        self.run_cli(["notice", "archive", "1"], None, None)
        code, after, err = self.run_cli(["brief"], "sess-2", self.repo_dir)
        self.assertEqual(before, after)


if __name__ == "__main__":
    import unittest

    unittest.main()
