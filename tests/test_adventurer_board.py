import json
import os

from guild import context, db, paths, timeutil
from guild.commands import board as board_commands
from tests.mq_fixtures import OPEN_VIEW
from tests.test_adventurer import AdventurerTestCase


class AdventurerBoardTests(AdventurerTestCase):
    def _model(self):
        conn = db.connect(paths.db_path())
        self.addCleanup(conn.close)
        ctx = context.RunContext(
            conn,
            None,
            None,
            timeutil.utcnow(),
            None,
            paths.claude_sessions_dir(),
            paths.projects_config_dir(),
            paths.state_dir(),
        )
        return board_commands.board_model(ctx)

    def _board_text(self):
        code, out, err = self.cli(["board"], None)
        self.assertEqual(code, 0, err)
        return out

    def test_model_carries_linked_ideas_both_ways(self):
        self.start("adv-1", "fix typo", "--task", "demo-epic/T02")
        self.cli(["idea", "add", "Dark mode", "--description", "d"], None)
        self.cli(["idea", "link", "1"], "adv-1")
        model = self._model()
        self.assertEqual(model["adventurers"][0]["ideas"], [{"id": 1, "title": "Dark mode"}])
        self.assertEqual(model["ideas"][0]["adventurers"], [{"id": 1, "state": "active", "has_prs": False}])

    def test_active_adventurer_is_listed_with_liveness_and_prs(self):
        self.write_gh_fixture("view_acme-app_7", dict(OPEN_VIEW))
        self.start("adv-1", "fix typo", "--task", "demo-epic/T02")
        code, out, err = self.cli(
            ["pr", "track", "acme/app#7", "--task", "demo-epic/T02", "--what", "typo", "--waits", "review"], "adv-1"
        )
        self.assertEqual(code, 0, err)
        entry = self._model()["adventurers"][0]
        self.assertEqual(
            (entry["id"], entry["job"], entry["task"], entry["state"]), (1, "fix typo", "demo-epic/T02", "active")
        )
        self.assertEqual(entry["project"], "acme")
        self.assertEqual([pr["number"] for pr in entry["prs"]], [7])
        self.assertTrue(entry["stopped_without_report"])
        self.assertFalse(entry["live"])

    def test_live_session_is_not_flagged(self):
        self.start("adv-1", "x", "--task", "demo-epic/T90")
        self.write_session(os.getpid(), "adv-1", "adv")
        entry = self._model()["adventurers"][0]
        self.assertTrue(entry["live"])
        self.assertFalse(entry["stopped_without_report"])

    def test_done_stays_listed_until_dismissed(self):
        self.start("adv-1", "x", "--task", "demo-epic/T90")
        self.cli(["adventurer", "done", "--pending", "left the tests"], "adv-1")
        entry = self._model()["adventurers"][0]
        self.assertEqual(
            (entry["state"], entry["pending"], entry["stopped_without_report"]), ("done", "left the tests", False)
        )
        code, out, err = self.cli(["adventurer", "dismiss", "1"], None)
        self.assertEqual(code, 0, err)
        self.assertEqual(self._model()["adventurers"], [])
        self.assertNotIn("adventurer 1", self._board_text())

    def test_dismiss_refusals(self):
        self.start("adv-1", "x", "--task", "demo-epic/T90")
        self.write_session(os.getpid(), "adv-1", "adv")
        code, out, err = self.cli(["adventurer", "dismiss", "1"], None)
        self.assertEqual(code, 1)
        self.assertIn("session is alive", err)
        self.assertEqual(self.cli(["adventurer", "dismiss", "9"], None)[0], 1)
        self.cli(["adventurer", "done", "--pending", "none"], "adv-1")
        self.cli(["adventurer", "dismiss", "1"], None)
        self.assertEqual(self.cli(["adventurer", "dismiss", "1"], None)[0], 1)

    def test_dismiss_survives_rebuild(self):
        self.start("adv-1", "x", "--task", "demo-epic/T90")
        self.cli(["adventurer", "done", "--pending", "none"], "adv-1")
        self.cli(["adventurer", "dismiss", "1"], None)
        self.assertEqual(self.cli(["rebuild"], None)[0], 0)
        self.assertEqual(self.rows("SELECT state FROM adventurers")[0]["state"], "dismissed")
        self.assertEqual(self._model()["adventurers"], [])

    def test_cli_board_lists_adventurers_and_the_flag(self):
        self.start("adv-1", "fix typo", "--task", "demo-epic/T02")
        text = self._board_text()
        for expected in ("adventurer 1", "fix typo", "demo-epic/T02", "stopped without report"):
            self.assertIn(expected, text)
        self.cli(["adventurer", "done", "--pending", "ping the owner"], "adv-1")
        text = self._board_text()
        self.assertIn("pending: ping the owner", text)
        self.assertNotIn("stopped without report", text)

    def test_party_without_live_leader_is_flagged_until_handed_off(self):
        self.cli(
            ["party", "start", "alpha", "--reason", "test reason", "--goal", "test goal", "--done-when", "test done"],
            "sess-1",
        )
        party = self._model()["parties"][0]
        self.assertTrue(party["stopped_without_report"])
        self.assertIn("stopped without report", self._board_text())
        self.cli(["handoff", "--in-flight", "x", "--learned", "y"], "sess-1")
        party = self._model()["parties"][0]
        self.assertEqual(party["state"], "awaiting-leader")
        self.assertFalse(party["stopped_without_report"])

    def test_party_with_live_leader_is_not_flagged(self):
        self.cli(
            ["party", "start", "alpha", "--reason", "test reason", "--goal", "test goal", "--done-when", "test done"],
            "sess-1",
        )
        self.write_session(os.getpid(), "sess-1", "lead")
        self.assertFalse(self._model()["parties"][0]["stopped_without_report"])


class PartyClosePendingTests(AdventurerTestCase):
    def setUp(self):
        super().setUp()
        self.cli(
            ["party", "start", "alpha", "--reason", "test reason", "--goal", "test goal", "--done-when", "test done"],
            "sess-1",
        )

    def test_close_without_pending_fails(self):
        code, out, err = self.cli(["party", "close", "alpha"], None)
        self.assertEqual(code, 2)
        self.assertEqual(self.rows("SELECT state FROM parties")[0]["state"], "active")

    def test_close_validates_pending_like_handoff(self):
        self.assertEqual(self.cli(["party", "close", "alpha", "--pending", " "], None)[0], 1)
        self.assertEqual(self.cli(["party", "close", "alpha", "--pending", "mail me@x.com"], None)[0], 1)
        self.assertEqual(self.rows("SELECT state FROM parties")[0]["state"], "active")

    def test_pending_is_stored_on_the_event(self):
        code, out, err = self.cli(["party", "close", "alpha", "--pending", "none"], None)
        self.assertEqual(code, 0, err)
        row = self.rows("SELECT payload FROM events WHERE kind = 'party.closed'")[0]
        self.assertEqual(json.loads(row["payload"])["pending"], "none")
