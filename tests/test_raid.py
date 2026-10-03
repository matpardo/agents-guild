import sqlite3
import unittest
from datetime import timedelta
from unittest import mock

from guild import timeutil
from guild.commands import raid as raid_commands
from tests.testutil import GuildTestCase


class RaidRoleLabelTests(unittest.TestCase):
    def test_solo_when_no_raids(self):
        self.assertEqual(raid_commands.raid_role_label([]), "solo")

    def test_member_shows_raid_name(self):
        self.assertEqual(raid_commands.raid_role_label([{"raid": "infra", "lead": 0}]), "infra")

    def test_lead_is_prefixed(self):
        self.assertEqual(raid_commands.raid_role_label([{"raid": "infra", "lead": 1}]), "RL infra")

    def test_multiple_sorted_by_name(self):
        rows = [{"raid": "zeta", "lead": 0}, {"raid": "infra", "lead": 1}]
        self.assertEqual(raid_commands.raid_role_label(rows), "RL infra, zeta")


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

    def test_join_requires_ttl_or_until_leave(self):
        code, out, err = self.run_cli(["raid", "join", "ci"], "sess-1", self.repo_dir)
        self.assertEqual(code, 2)
        self.assertIn("one of the arguments --ttl --until-leave is required", err)

    def test_join_rejects_both_ttl_and_until_leave(self):
        code, out, err = self.run_cli(
            ["raid", "join", "ci", "--ttl", "1h", "--until-leave"], "sess-1", self.repo_dir
        )
        self.assertEqual(code, 2)
        self.assertIn("not allowed with argument", err)

    def _raid_member_row(self, raid_name, party):
        conn = sqlite3.connect(str(self.data_home / "guild" / "guild.db"))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT expires_at FROM raid_members WHERE raid = ? AND party = ?", (raid_name, party)
        ).fetchone()
        conn.close()
        return row

    def test_join_until_leave_stores_null_expiry(self):
        code, out, err = self.run_cli(
            ["raid", "join", "ci", "--until-leave"], "sess-1", self.repo_dir
        )
        self.assertEqual(code, 0, err)
        self.assertIn("party 'alpha' joined raid 'ci' until leave", out)
        row = self._raid_member_row("ci", "alpha")
        self.assertIsNone(row["expires_at"])

    def test_until_leave_never_expires(self):
        self.run_cli(["raid", "join", "ci", "--until-leave"], "sess-1", self.repo_dir)
        far_future = timeutil.utcnow() + timedelta(days=365)
        with mock.patch("guild.timeutil.utcnow", return_value=far_future):
            code, out, err = self.run_cli(["raids"], None, None)
        self.assertIn("ci:", out)
        self.assertIn("alpha (until leave)", out)

    def test_until_leave_member_can_still_leave(self):
        self.run_cli(["raid", "join", "ci", "--until-leave"], "sess-1", self.repo_dir)
        far_future = timeutil.utcnow() + timedelta(days=365)
        with mock.patch("guild.timeutil.utcnow", return_value=far_future):
            code, out, err = self.run_cli(["raid", "leave", "ci"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        self.assertIn("party 'alpha' left raid 'ci'", out)

    def test_ttl_join_then_until_leave_switches_mode(self):
        self.run_cli(["raid", "join", "ci", "--ttl", "30m"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(
            ["raid", "join", "ci", "--until-leave"], "sess-1", self.repo_dir
        )
        self.assertEqual(code, 0, err)
        row = self._raid_member_row("ci", "alpha")
        self.assertIsNone(row["expires_at"])

    def test_until_leave_then_ttl_switches_mode(self):
        self.run_cli(["raid", "join", "ci", "--until-leave"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["raid", "join", "ci", "--ttl", "1h"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        row = self._raid_member_row("ci", "alpha")
        self.assertIsNotNone(row["expires_at"])

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

    def test_until_leave_member_receives_notice_long_after_ttl_would_have_expired(self):
        self.run_cli(["raid", "join", "ci", "--until-leave"], "sess-1", self.repo_dir)
        self.run_cli(["raid", "join", "ci", "--ttl", "1h"], "sess-2", self.repo_dir)
        far_future = timeutil.utcnow() + timedelta(days=10)
        with mock.patch("guild.timeutil.utcnow", return_value=far_future):
            self.run_cli(
                ["notice", "create", "ci flaky", "--to", "raid:ci", "--ttl", "1h"], "sess-2", self.repo_dir
            )
            code, out, err = self.run_cli(["inbox", "--since-last"], "sess-1", self.repo_dir)
        self.assertIn("ci flaky", out)


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

    def test_board_shows_until_leave_membership(self):
        repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha"], "sess-1", repo_dir)
        self.run_cli(["raid", "join", "ci", "--until-leave"], "sess-1", repo_dir)
        code, out, err = self.run_cli(["board"], None, None)
        self.assertEqual(code, 0, err)
        self.assertIn("raids: ci (until leave)", out)


class BoardRaidFilterTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha"], "sess-1", self.repo_dir)
        self.run_cli(["party", "start", "beta"], "sess-2", self.repo_dir)
        self.run_cli(["raid", "join", "ci", "--ttl", "1h"], "sess-1", self.repo_dir)

    def test_shows_only_raid_member_parties(self):
        code, out, err = self.run_cli(["board", "--raid", "ci"], None, None)
        self.assertEqual(code, 0, err)
        self.assertIn("━━ alpha", out)
        self.assertNotIn("━━ beta", out)

    def test_shows_asks_only_from_raid_members(self):
        self.run_cli(["quest", "add", "demo-a", "--title", "A", "--no-epic"], "sess-1", self.repo_dir)
        self.run_cli(["task", "add", "demo-a/T01", "--title", "First"], "sess-1", self.repo_dir)
        self.run_cli(
            ["ask", "alpha ready?", "--context", "x", "--ref", "task:demo-a/T01"], "sess-1", self.repo_dir
        )
        self.run_cli(["quest", "add", "demo-b", "--title", "B", "--no-epic"], "sess-2", self.repo_dir)
        self.run_cli(["task", "add", "demo-b/T01", "--title", "First"], "sess-2", self.repo_dir)
        self.run_cli(
            ["ask", "beta ready?", "--context", "x", "--ref", "task:demo-b/T01"], "sess-2", self.repo_dir
        )
        code, out, err = self.run_cli(["board", "--raid", "ci"], None, None)
        self.assertEqual(code, 0, err)
        self.assertIn("alpha ready?", out)
        self.assertNotIn("beta ready?", out)

    def test_shows_only_notices_scoped_to_that_raid(self):
        self.run_cli(
            ["notice", "create", "ci flaky", "--to", "raid:ci", "--ttl", "1h"], "sess-1", self.repo_dir
        )
        self.run_cli(["notice", "create", "guild wide", "--to", "guild", "--ttl", "1h"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["board", "--raid", "ci"], None, None)
        self.assertEqual(code, 0, err)
        self.assertIn("ci flaky", out)
        self.assertNotIn("guild wide", out)

    def test_shows_claims_only_of_raid_members(self):
        self.run_cli(["claim", "src/a.py", "--ttl", "30m"], "sess-1", self.repo_dir)
        self.run_cli(["claim", "src/b.py", "--ttl", "30m"], "sess-2", self.repo_dir)
        code, out, err = self.run_cli(["board", "--raid", "ci"], None, None)
        self.assertEqual(code, 0, err)
        self.assertIn("src/a.py", out)
        self.assertNotIn("src/b.py", out)

    def test_unknown_raid_is_a_clear_error(self):
        code, out, err = self.run_cli(["board", "--raid", "ghost"], None, None)
        self.assertEqual(code, 1)
        self.assertIn("raid 'ghost' has no active members", err)

    def test_empty_raid_is_a_clear_error(self):
        future = timeutil.utcnow() + timedelta(hours=2)
        with mock.patch("guild.timeutil.utcnow", return_value=future):
            code, out, err = self.run_cli(["board", "--raid", "ci"], None, None)
        self.assertEqual(code, 1)
        self.assertIn("raid 'ci' has no active members", err)

    def test_party_and_raid_are_mutually_exclusive(self):
        code, out, err = self.run_cli(
            ["board", "--party", "alpha", "--raid", "ci"], None, None
        )
        self.assertEqual(code, 2)
        self.assertIn("not allowed with argument", err)


class RaidPartyCloseTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha"], "sess-1", self.repo_dir)
        self.run_cli(["raid", "join", "ci", "--ttl", "5h"], "sess-1", self.repo_dir)
        self.run_cli(["raid", "join", "ci-ul", "--until-leave"], "sess-1", self.repo_dir)

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

    def test_close_leaves_until_leave_raid(self):
        code, out, err = self.run_cli(["party", "close", "alpha"], None, None)
        self.assertEqual(code, 0, err)
        self.assertIsNone(
            self._row("SELECT raid FROM raid_members WHERE raid = ? AND party = ?", ("ci-ul", "alpha"))
        )

    def test_rebuild_reproduces_raid_cascade(self):
        self.run_cli(["party", "close", "alpha"], None, None)
        self.run_cli(["rebuild"], None, None)
        self.assertIsNone(
            self._row("SELECT raid FROM raid_members WHERE raid = ? AND party = ?", ("ci", "alpha"))
        )

    def test_rebuild_reproduces_until_leave_membership(self):
        self.run_cli(["rebuild"], None, None)
        row = self._row(
            "SELECT expires_at FROM raid_members WHERE raid = ? AND party = ?", ("ci-ul", "alpha")
        )
        self.assertIsNone(row["expires_at"])


class RaidLeadTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha"], "sess-1", self.repo_dir)
        self.run_cli(["party", "start", "beta"], "sess-2", self.repo_dir)

    def _raid_member_row(self, raid_name, party):
        conn = sqlite3.connect(str(self.data_home / "guild" / "guild.db"))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT lead, expires_at FROM raid_members WHERE raid = ? AND party = ?",
            (raid_name, party),
        ).fetchone()
        conn.close()
        return row

    def test_join_with_lead_becomes_lead(self):
        code, out, err = self.run_cli(
            ["raid", "join", "ci", "--ttl", "1h", "--lead"], "sess-1", self.repo_dir
        )
        self.assertEqual(code, 0, err)
        row = self._raid_member_row("ci", "alpha")
        self.assertEqual(row["lead"], 1)

    def test_second_party_lead_fails_naming_current_lead(self):
        self.run_cli(["raid", "join", "ci", "--ttl", "1h", "--lead"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(
            ["raid", "join", "ci", "--ttl", "1h", "--lead"], "sess-2", self.repo_dir
        )
        self.assertEqual(code, 1)
        self.assertIn("already has a lead: party 'alpha'", err)

    def test_same_party_rejoining_with_lead_is_fine(self):
        self.run_cli(["raid", "join", "ci", "--ttl", "1h", "--lead"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(
            ["raid", "join", "ci", "--ttl", "8h", "--lead"], "sess-1", self.repo_dir
        )
        self.assertEqual(code, 0, err)
        row = self._raid_member_row("ci", "alpha")
        self.assertEqual(row["lead"], 1)

    def test_plain_renewal_keeps_lead_status(self):
        self.run_cli(["raid", "join", "ci", "--ttl", "1h", "--lead"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["raid", "join", "ci", "--ttl", "8h"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        row = self._raid_member_row("ci", "alpha")
        self.assertEqual(row["lead"], 1)

    def test_non_lead_member_joining_plainly_stays_non_lead(self):
        self.run_cli(["raid", "join", "ci", "--ttl", "1h", "--lead"], "sess-1", self.repo_dir)
        self.run_cli(["raid", "join", "ci", "--ttl", "1h"], "sess-2", self.repo_dir)
        row = self._raid_member_row("ci", "beta")
        self.assertEqual(row["lead"], 0)

    def test_lead_handover_after_leave(self):
        self.run_cli(["raid", "join", "ci", "--ttl", "1h", "--lead"], "sess-1", self.repo_dir)
        self.run_cli(["raid", "leave", "ci"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(
            ["raid", "join", "ci", "--ttl", "1h", "--lead"], "sess-2", self.repo_dir
        )
        self.assertEqual(code, 0, err)
        row = self._raid_member_row("ci", "beta")
        self.assertEqual(row["lead"], 1)

    def test_lead_handover_after_close(self):
        self.run_cli(["raid", "join", "ci", "--ttl", "1h", "--lead"], "sess-1", self.repo_dir)
        self.run_cli(["party", "close", "alpha"], None, None)
        code, out, err = self.run_cli(
            ["raid", "join", "ci", "--ttl", "1h", "--lead"], "sess-2", self.repo_dir
        )
        self.assertEqual(code, 0, err)

    def test_lead_handover_after_expiry(self):
        self.run_cli(["raid", "join", "ci", "--ttl", "30m", "--lead"], "sess-1", self.repo_dir)
        future = timeutil.utcnow() + timedelta(hours=1)
        with mock.patch("guild.timeutil.utcnow", return_value=future):
            code, out, err = self.run_cli(
                ["raid", "join", "ci", "--ttl", "1h", "--lead"], "sess-2", self.repo_dir
            )
        self.assertEqual(code, 0, err)

    def test_raids_shows_lead_marker(self):
        self.run_cli(["raid", "join", "ci", "--ttl", "1h", "--lead"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["raids"], None, None)
        self.assertIn("alpha (lead,", out)

    def test_board_shows_lead_marker(self):
        self.run_cli(["raid", "join", "ci", "--ttl", "1h", "--lead"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["board"], None, None)
        self.assertIn("raids: ci (lead,", out)

    def test_brief_shows_lead_for_every_member(self):
        self.run_cli(["raid", "join", "ci", "--ttl", "1h", "--lead"], "sess-1", self.repo_dir)
        self.run_cli(["raid", "join", "ci", "--ttl", "1h"], "sess-2", self.repo_dir)
        code, out, err = self.run_cli(["brief"], "sess-2", self.repo_dir)
        self.assertEqual(code, 0, err)
        self.assertIn("raid ci — lead: alpha", out)

    def test_ask_reaches_lead_inbox(self):
        self.run_cli(["raid", "join", "ci", "--ttl", "1h", "--lead"], "sess-1", self.repo_dir)
        self.run_cli(["raid", "join", "ci", "--ttl", "1h"], "sess-2", self.repo_dir)
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-2", self.repo_dir)
        self.run_cli(["task", "add", "demo/T01", "--title", "First"], "sess-2", self.repo_dir)
        self.run_cli(
            ["ask", "ready?", "--context", "x", "--ref", "task:demo/T01"], "sess-2", self.repo_dir
        )
        code, out, err = self.run_cli(["inbox", "--since-last"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        self.assertIn('- ask #1 from beta (raid ci): "ready?"', out)

    def test_ask_does_not_reach_non_lead_member(self):
        self.run_cli(["raid", "join", "ci", "--ttl", "1h", "--lead"], "sess-1", self.repo_dir)
        self.run_cli(["raid", "join", "ci", "--ttl", "1h"], "sess-2", self.repo_dir)
        self.run_cli(["party", "start", "gamma"], "sess-3", self.repo_dir)
        self.run_cli(["raid", "join", "ci", "--ttl", "1h"], "sess-3", self.repo_dir)
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-2", self.repo_dir)
        self.run_cli(["task", "add", "demo/T01", "--title", "First"], "sess-2", self.repo_dir)
        self.run_cli(
            ["ask", "ready?", "--context", "x", "--ref", "task:demo/T01"], "sess-2", self.repo_dir
        )
        code, out, err = self.run_cli(["inbox", "--since-last"], "sess-3", self.repo_dir)
        self.assertEqual(code, 0, err)
        self.assertEqual(out, "")

    def test_ask_does_not_reach_asker_itself(self):
        self.run_cli(["raid", "join", "ci", "--ttl", "1h", "--lead"], "sess-1", self.repo_dir)
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", self.repo_dir)
        self.run_cli(["task", "add", "demo/T01", "--title", "First"], "sess-1", self.repo_dir)
        self.run_cli(
            ["ask", "ready?", "--context", "x", "--ref", "task:demo/T01"], "sess-1", self.repo_dir
        )
        code, out, err = self.run_cli(["inbox", "--since-last"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        self.assertEqual(out, "")

    def test_ask_reaches_lead_only_once(self):
        self.run_cli(["raid", "join", "ci", "--ttl", "1h", "--lead"], "sess-1", self.repo_dir)
        self.run_cli(["raid", "join", "ci", "--ttl", "1h"], "sess-2", self.repo_dir)
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-2", self.repo_dir)
        self.run_cli(["task", "add", "demo/T01", "--title", "First"], "sess-2", self.repo_dir)
        self.run_cli(
            ["ask", "ready?", "--context", "x", "--ref", "task:demo/T01"], "sess-2", self.repo_dir
        )
        self.run_cli(["inbox", "--since-last"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["inbox", "--since-last"], "sess-1", self.repo_dir)
        self.assertEqual(out, "")

    def test_bound_lead_session_can_answer_ask_and_asker_receives_it(self):
        self.run_cli(["raid", "join", "ci", "--ttl", "1h", "--lead"], "sess-1", self.repo_dir)
        self.run_cli(["raid", "join", "ci", "--ttl", "1h"], "sess-2", self.repo_dir)
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-2", self.repo_dir)
        self.run_cli(["task", "add", "demo/T01", "--title", "First"], "sess-2", self.repo_dir)
        self.run_cli(
            ["ask", "ready?", "--context", "x", "--ref", "task:demo/T01"], "sess-2", self.repo_dir
        )
        code, out, err = self.run_cli(["answer", "1", "yes, lead says go"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        code, out, err = self.run_cli(["inbox", "--since-last"], "sess-2", self.repo_dir)
        self.assertIn('- ask #1 answered by human: "yes, lead says go"', out)

    def test_rebuild_reproduces_lead(self):
        self.run_cli(["raid", "join", "ci", "--ttl", "1h", "--lead"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["rebuild"], None, None)
        self.assertEqual(code, 0, err)
        row = self._raid_member_row("ci", "alpha")
        self.assertEqual(row["lead"], 1)


if __name__ == "__main__":
    import unittest

    unittest.main()
