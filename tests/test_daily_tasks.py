from datetime import datetime, timedelta, timezone
from unittest import mock

from guild.commands import board as board_commands
from tests.test_quest_board import QuestBoardTestCase

_NOW = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)


def _day(days_ago):
    return (_NOW - timedelta(days=days_ago)).astimezone().date().isoformat()


class DailyTasksTests(QuestBoardTestCase):
    def at(self, days_ago, argv, session_id):
        with mock.patch("guild.timeutil.utcnow", return_value=_NOW - timedelta(days=days_ago)):
            return self.ok(argv, session_id)

    def board(self, argv):
        with mock.patch("guild.timeutil.utcnow", return_value=_NOW):
            return self.ok(["board", *argv], None)

    def add_quest(self, days_ago, slug, session_id):
        self.at(
            days_ago,
            ["quest", "add", slug, "--title", slug, "--no-epic", "--tasks", "T01,T02", "--titles", "one,two"],
            session_id,
        )

    def setUp(self):
        super().setUp()
        self.at(20, ["party", "start", "alpha", "--reason", "r"], "sess-1")
        self.add_quest(16, "old", "sess-1")
        self.at(3, ["task", "add", "old/T03", "--title", "three"], "sess-1")
        self.at(3, ["task", "done", "old/T01", "--summary", "s"], "sess-1")
        self.at(0, ["task", "done", "old/T03", "--summary", "s"], "sess-1")

    def party_days(self, name):
        with mock.patch("guild.timeutil.utcnow", return_value=_NOW):
            model = board_commands.board_model(self.ctx())
        return next(party for party in model["parties"] if party["name"] == name)["daily_tasks"]

    def test_party_model_counts_created_and_done_tasks_per_day_for_fifteen_days(self):
        days = self.party_days("alpha")
        self.assertEqual(len(days), 15)
        self.assertEqual(days[0]["day"], _day(14))
        self.assertEqual(days[-1], {"day": _day(0), "created": 0, "done": 1, "active": True})
        self.assertEqual(days[-4], {"day": _day(3), "created": 1, "done": 1, "active": True})
        self.assertEqual(sum(day["created"] for day in days), 1)
        self.assertEqual(sum(day["done"] for day in days), 2)

    def test_days_without_a_session_event_are_inactive(self):
        days = self.party_days("alpha")
        self.assertEqual([day["day"] for day in days if day["active"]], [_day(3), _day(0)])

    def test_session_that_produced_nothing_shows_zero_not_a_dash(self):
        self.at(1, ["task", "start", "old/T02"], "sess-1")
        out = self.board(["--party", "alpha"])
        created_line = next(line for line in out.splitlines() if line.strip().startswith("created"))
        self.assertEqual(created_line.split()[-2], "0")

    def test_other_party_tasks_stay_out_of_the_party_counts(self):
        self.at(10, ["party", "start", "beta", "--reason", "r"], "sess-2")
        self.add_quest(1, "fresh", "sess-2")
        self.assertEqual(sum(day["created"] for day in self.party_days("alpha")), 1)
        self.assertEqual(self.party_days("beta")[-2]["created"], 2)

    def test_party_board_prints_the_daily_rows(self):
        out = self.board(["--party", "alpha"])
        self.assertIn("TASKS PER DAY · last 15 days", out)
        created_line = next(line for line in out.splitlines() if line.strip().startswith("created"))
        done_line = next(line for line in out.splitlines() if line.strip().startswith("done "))
        self.assertEqual(created_line.split()[1:], ["-"] * 11 + ["1", "-", "-", "0"])
        self.assertEqual(done_line.split()[1:], ["-"] * 11 + ["1", "-", "-", "1"])

    def test_raid_board_sums_its_member_parties(self):
        self.at(10, ["party", "start", "beta", "--reason", "r"], "sess-2")
        self.add_quest(3, "fresh", "sess-2")
        self.at(1, ["raid", "join", "ci", "--ttl", "30d"], "sess-1")
        self.at(1, ["raid", "join", "ci", "--ttl", "30d"], "sess-2")
        out = self.board(["--raid", "ci"])
        created_line = next(line for line in out.splitlines() if line.strip().startswith("created"))
        self.assertEqual(created_line.split()[-4], "3")
        self.assertEqual(created_line.split()[-2], "0")
        self.assertEqual(created_line.split()[-5], "-")

    def test_full_board_has_no_daily_rows(self):
        self.assertNotIn("TASKS PER DAY", self.board([]))
