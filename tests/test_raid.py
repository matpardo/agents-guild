import sqlite3
from datetime import timedelta
from unittest import mock

from guild import timeutil
from tests.testutil import GuildTestCase


class RaidJoinLeaveTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha"], "sess-1", self.repo_dir)

    def test_join_requires_binding(self):
        code, out, err = self.run_cli(["raid", "join", "ci", "--ttl", "1h"], None, None)
        self.assertEqual(code, 1)
        self.assertIn("session not bound", err)

    def test_join_rejects_invalid_name(self):
        code, out, err = self.run_cli(["raid", "join", "../ci", "--ttl", "1h"], "sess-1", self.repo_dir)
        self.assertEqual(code, 1)
        self.assertIn("invalid raid name", err)

    def test_join_and_list(self):
        code, out, err = self.run_cli(["raid", "join", "ci", "--ttl", "1h"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        self.assertIn("party 'alpha' joined raid 'ci'", out)
        code, out, err = self.run_cli(["raids"], None, None)
        self.assertIn("ci:", out)
        self.assertIn("alpha", out)

    def test_join_again_refreshes_ttl(self):
        self.run_cli(["raid", "join", "ci", "--ttl", "30m"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["raid", "join", "ci", "--ttl", "8h"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        conn = sqlite3.connect(str(self.data_home / "guild" / "guild.db"))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT expires_at FROM raid_members WHERE raid = ? AND party = ?", ("ci", "alpha")
        ).fetchone()
        conn.close()
        self.assertTrue(row["expires_at"] > timeutil.to_iso(timeutil.utcnow() + timedelta(hours=1)))

    def test_leave_requires_binding(self):
        code, out, err = self.run_cli(["raid", "leave", "ci"], None, None)
        self.assertEqual(code, 1)
        self.assertIn("session not bound", err)

    def test_leave_when_not_a_member_fails(self):
        code, out, err = self.run_cli(["raid", "leave", "ci"], "sess-1", self.repo_dir)
        self.assertEqual(code, 1)
        self.assertIn("is not a member of raid 'ci'", err)

    def test_join_then_leave(self):
        self.run_cli(["raid", "join", "ci", "--ttl", "1h"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["raid", "leave", "ci"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        self.assertIn("party 'alpha' left raid 'ci'", out)
        code, out, err = self.run_cli(["raids"], None, None)
        self.assertEqual(out, "")

    def test_leave_after_expiry_fails(self):
        self.run_cli(["raid", "join", "ci", "--ttl", "30m"], "sess-1", self.repo_dir)
        future = timeutil.utcnow() + timedelta(hours=1)
        with mock.patch("guild.timeutil.utcnow", return_value=future):
            code, out, err = self.run_cli(["raid", "leave", "ci"], "sess-1", self.repo_dir)
        self.assertEqual(code, 1)
        self.assertIn("is not a member of raid 'ci'", err)

    def test_expired_member_not_listed(self):
        self.run_cli(["raid", "join", "ci", "--ttl", "30m"], "sess-1", self.repo_dir)
        future = timeutil.utcnow() + timedelta(hours=1)
        with mock.patch("guild.timeutil.utcnow", return_value=future):
            code, out, err = self.run_cli(["raids"], None, None)
        self.assertEqual(out, "")


class RaidNoticeTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha"], "sess-1", self.repo_dir)
        self.run_cli(["party", "start", "beta"], "sess-2", self.repo_dir)

    def test_notice_to_empty_raid_fails(self):
        code, out, err = self.run_cli(
            ["notice", "create", "ci flaky", "--to", "raid:ci", "--ttl", "1h"], "sess-1", self.repo_dir
        )
        self.assertEqual(code, 1)
        self.assertIn("no active members", err)

    def test_notice_to_raid_with_member_succeeds(self):
        self.run_cli(["raid", "join", "ci", "--ttl", "1h"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(
            ["notice", "create", "ci flaky", "--to", "raid:ci", "--ttl", "1h"], "sess-1", self.repo_dir
        )
        self.assertEqual(code, 0, err)

    def test_raid_member_receives_notice(self):
        self.run_cli(["raid", "join", "ci", "--ttl", "1h"], "sess-1", self.repo_dir)
        self.run_cli(["raid", "join", "ci", "--ttl", "1h"], "sess-2", self.repo_dir)
        self.run_cli(
            ["notice", "create", "ci flaky", "--to", "raid:ci", "--ttl", "1h"], "sess-1", self.repo_dir
        )
        code, out, err = self.run_cli(["inbox", "--since-last"], "sess-2", self.repo_dir)
        self.assertEqual(code, 0)
        self.assertIn("ci flaky", out)

    def test_non_member_does_not_receive_notice(self):
        self.run_cli(["raid", "join", "ci", "--ttl", "1h"], "sess-1", self.repo_dir)
        self.run_cli(
            ["notice", "create", "ci flaky", "--to", "raid:ci", "--ttl", "1h"], "sess-1", self.repo_dir
        )
        code, out, err = self.run_cli(["inbox", "--since-last"], "sess-2", self.repo_dir)
        self.assertEqual(out, "")

    def test_sender_does_not_receive_own_notice(self):
        self.run_cli(["raid", "join", "ci", "--ttl", "1h"], "sess-1", self.repo_dir)
        self.run_cli(
            ["notice", "create", "ci flaky", "--to", "raid:ci", "--ttl", "1h"], "sess-1", self.repo_dir
        )
        code, out, err = self.run_cli(["inbox", "--since-last"], "sess-1", self.repo_dir)
        self.assertEqual(out, "")

    def test_expired_member_does_not_receive_notice(self):
        self.run_cli(["raid", "join", "ci", "--ttl", "1h"], "sess-1", self.repo_dir)
        self.run_cli(["raid", "join", "ci", "--ttl", "30m"], "sess-2", self.repo_dir)
        self.run_cli(
            ["notice", "create", "ci flaky", "--to", "raid:ci", "--ttl", "1h"], "sess-1", self.repo_dir
        )
        future = timeutil.utcnow() + timedelta(minutes=45)
        with mock.patch("guild.timeutil.utcnow", return_value=future):
            code, out, err = self.run_cli(["inbox", "--since-last"], "sess-2", self.repo_dir)
        self.assertEqual(out, "")

    def test_unbound_session_does_not_receive_raid_notice(self):
        self.run_cli(["raid", "join", "ci", "--ttl", "1h"], "sess-1", self.repo_dir)
        self.run_cli(
            ["notice", "create", "ci flaky", "--to", "raid:ci", "--ttl", "1h"], "sess-1", self.repo_dir
        )
        code, out, err = self.run_cli(["inbox", "--since-last"], "sess-3", self.repo_dir)
        self.assertEqual(out, "")

    def test_human_terminal_does_not_receive_raid_notice(self):
        self.run_cli(["raid", "join", "ci", "--ttl", "1h"], "sess-1", self.repo_dir)
        self.run_cli(
            ["notice", "create", "ci flaky", "--to", "raid:ci", "--ttl", "1h"], "sess-1", self.repo_dir
        )
        code, out, err = self.run_cli(["inbox", "--since-last"], None, self.repo_dir)
        self.assertEqual(out, "")

    def test_raid_member_gets_notice_via_prompt_submit_hook(self):
        self.run_cli(["raid", "join", "ci", "--ttl", "1h"], "sess-1", self.repo_dir)
        self.run_cli(["raid", "join", "ci", "--ttl", "1h"], "sess-2", self.repo_dir)
        self.run_cli(
            ["notice", "create", "ci flaky", "--to", "raid:ci", "--ttl", "1h"], "sess-1", self.repo_dir
        )
        code, out, err = self.run_hook("prompt-submit", {"session_id": "sess-2", "cwd": str(self.repo_dir)})
        self.assertIn("ci flaky", out)

    def test_non_member_gets_nothing_via_post_tool_use_hook(self):
        self.run_cli(["raid", "join", "ci", "--ttl", "1h"], "sess-1", self.repo_dir)
        self.run_cli(
            ["notice", "create", "ci flaky", "--to", "raid:ci", "--ttl", "1h"], "sess-1", self.repo_dir
        )
        code, out, err = self.run_hook("post-tool-use", {"session_id": "sess-2", "cwd": str(self.repo_dir)})
        self.assertEqual(out, "")


class RaidBoardTests(GuildTestCase):
    def test_board_shows_raid_scope_and_party_membership(self):
        repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha"], "sess-1", repo_dir)
        self.run_cli(["raid", "join", "ci", "--ttl", "5h"], "sess-1", repo_dir)
        self.run_cli(
            ["notice", "create", "ci flaky", "--to", "raid:ci", "--ttl", "1h"], "sess-1", repo_dir
        )
        code, out, err = self.run_cli(["board"], None, None)
        self.assertEqual(code, 0, err)
        self.assertIn("raid:ci", out)
        self.assertIn("raids: ci (", out)
        self.assertIn("left)", out)


class RaidPartyCloseTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha"], "sess-1", self.repo_dir)
        self.run_cli(["raid", "join", "ci", "--ttl", "5h"], "sess-1", self.repo_dir)

    def _row(self, query, params):
        conn = sqlite3.connect(str(self.data_home / "guild" / "guild.db"))
        conn.row_factory = sqlite3.Row
        row = conn.execute(query, params).fetchone()
        conn.close()
        return row

    def test_close_leaves_all_raids(self):
        code, out, err = self.run_cli(["party", "close", "alpha"], None, None)
        self.assertEqual(code, 0, err)
        self.assertIsNone(
            self._row("SELECT raid FROM raid_members WHERE raid = ? AND party = ?", ("ci", "alpha"))
        )

    def test_rebuild_reproduces_raid_cascade(self):
        self.run_cli(["party", "close", "alpha"], None, None)
        self.run_cli(["rebuild"], None, None)
        self.assertIsNone(
            self._row("SELECT raid FROM raid_members WHERE raid = ? AND party = ?", ("ci", "alpha"))
        )


if __name__ == "__main__":
    import unittest

    unittest.main()
