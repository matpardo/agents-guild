import sqlite3
from datetime import datetime, timedelta, timezone
from unittest import mock

from guild import paths
from guild.commands import board as board_commands
from tests.test_quest_board import QuestBoardTestCase

_T0 = datetime(2026, 10, 24, 9, 0, tzinfo=timezone.utc)
_OPEN_VIEW = {"state": "OPEN", "isDraft": True, "headRefName": "feature/1", "title": "t"}


def _iso(minutes):
    return (_T0 + timedelta(minutes=minutes)).isoformat()


class ItemDatesTests(QuestBoardTestCase):
    def at(self, minutes, argv, session_id):
        with mock.patch("guild.timeutil.utcnow", return_value=_T0 + timedelta(minutes=minutes)):
            code, out, err = self.cli(argv, session_id)
        self.assertEqual(code, 0, err)
        return out

    def pr_row(self):
        return tuple(self.rows("SELECT tracked_at, last_activity_at FROM prs")[0])

    def claim_row(self, area):
        sql = "SELECT party, created_at, updated_at FROM claims WHERE area = '{}'".format(area)
        return tuple(self.rows(sql)[0])

    def party_updated(self, name):
        return self.rows("SELECT updated_at FROM parties WHERE name = '{}'".format(name))[0][0]

    def track_pr(self):
        self.write_gh_fixture("view_acme-app_1", dict(_OPEN_VIEW))
        self.at(0, ["quest", "add", "q1", "--open", "--title", "q1", "--epic", "demo-epic", "--tasks", "T02"], None)
        self.at(0, ["party", "start", "alpha", "--reason", "r"], "sess-1")
        self.at(1, ["quest", "take", "q1"], "sess-1")
        self.at(
            2,
            ["pr", "track", "acme/app#1", "--task", "q1/T02", "--what", "x", "--waits", "y"],
            "sess-1",
        )

    def test_pr_set_without_change_keeps_updated(self):
        self.track_pr()
        self.assertEqual(self.pr_row(), (_iso(2), _iso(2)))
        self.at(5, ["pr", "set", "acme/app#1", "--waits", "y"], "sess-1")
        self.assertEqual(self.pr_row(), (_iso(2), _iso(2)))
        self.at(6, ["pr", "set", "acme/app#1", "--waits", "z"], "sess-1")
        self.assertEqual(self.pr_row(), (_iso(2), _iso(6)))

    def test_claim_renewal_keeps_created_and_other_party_resets_it(self):
        self.start_party("alpha", "sess-1")
        self.start_party("beta", "sess-2")
        self.at(0, ["claim", "area:x", "--ttl", "1h"], "sess-1")
        self.assertEqual(self.claim_row("area:x"), ("alpha", _iso(0), _iso(0)))
        self.at(10, ["claim", "area:x", "--ttl", "1h"], "sess-1")
        self.assertEqual(self.claim_row("area:x"), ("alpha", _iso(0), _iso(10)))
        self.at(120, ["claim", "area:x", "--ttl", "1h"], "sess-2")
        self.assertEqual(self.claim_row("area:x"), ("beta", _iso(120), _iso(120)))

    def test_party_updated_moves_on_handoff_resume_and_close(self):
        self.at(0, ["party", "start", "alpha", "--reason", "r"], "sess-1")
        self.assertEqual(self.party_updated("alpha"), _iso(0))
        self.at(5, ["handoff", "--in-flight", "a", "--learned", "b"], "sess-1")
        self.assertEqual(self.party_updated("alpha"), _iso(5))
        self.at(8, ["party", "resume", "alpha"], "sess-2")
        self.assertEqual(self.party_updated("alpha"), _iso(8))
        self.at(12, ["party", "close", "--pending", "none"], "sess-2")
        self.assertEqual(self.party_updated("alpha"), _iso(12))

    def test_values_survive_rebuild_and_show_in_models(self):
        self.track_pr()
        self.at(3, ["claim", "area:x", "--ttl", "3000d"], "sess-1")
        self.at(4, ["claim", "area:x", "--ttl", "3000d"], "sess-1")
        self.at(4, ["pr", "set", "acme/app#1", "--waits", "z"], "sess-1")
        before = (self.pr_row(), self.claim_row("area:x"), self.party_updated("alpha"))
        self.ok(["rebuild"], None)
        self.assertEqual((self.pr_row(), self.claim_row("area:x"), self.party_updated("alpha")), before)
        party = board_commands.board_model(self.ctx())["parties"][0]
        self.assertTrue(party["dates"].startswith("created 2026"))
        self.assertIn("· updated", party["claims"][0]["dates"])
        self.assertIn("created 2026", self.at(30, ["claims"], "sess-1"))

    def test_doctor_counts_new_columns(self):
        self.track_pr()
        self.at(3, ["claim", "area:x", "--ttl", "1h"], "sess-1")
        raw = sqlite3.connect(str(paths.db_path()))
        raw.execute("UPDATE prs SET tracked_at = NULL")
        raw.execute("UPDATE claims SET created_at = NULL")
        raw.execute("UPDATE parties SET updated_at = NULL")
        raw.commit()
        raw.close()
        _, out, _ = self.run_cli(["doctor"], None, self.repo_dir)
        self.assertIn("3 rows predate stored dates", out)
