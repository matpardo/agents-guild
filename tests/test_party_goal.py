import json
import sqlite3

from guild import paths
from tests.mq_fixtures import OPEN_VIEW
from tests.test_adventurer import AdventurerTestCase

START = ["party", "start", "alpha", "--reason", "r"]
GOAL = ["--goal", "ship the goal", "--done-when", "all merged"]


class PartyGoalTestCase(AdventurerTestCase):
    def party(self):
        return self.rows("SELECT goal, done_when FROM parties WHERE name = 'alpha'")[0]

    def start_alpha(self):
        code, out, err = self.cli(START + GOAL, "sess-1")
        self.assertEqual(code, 0, err)


class StartTests(PartyGoalTestCase):
    def test_start_requires_both_flags(self):
        self.assertEqual(self.cli(START, "sess-1")[0], 2)
        self.assertEqual(self.cli(START + ["--goal", "g"], "sess-1")[0], 2)
        self.assertEqual(self.cli(START + ["--done-when", "d"], "sess-1")[0], 2)
        self.assertEqual(self.rows("SELECT * FROM parties"), [])

    def test_start_stores_trimmed_goal_and_done_when(self):
        self.assertEqual(self.cli(START + ["--goal", " g ", "--done-when", " d "], "sess-1")[0], 0)
        party = self.party()
        self.assertEqual((party["goal"], party["done_when"]), ("g", "d"))

    def test_blank_or_sensitive_values_are_refused(self):
        for goal, done_when in (("  ", "d"), ("g", "  "), ("mail me@x.com", "d"), ("g", "mail me@x.com")):
            code, out, err = self.cli(START + ["--goal", goal, "--done-when", done_when], "sess-1")
            self.assertEqual(code, 1, err)
        self.assertEqual(self.rows("SELECT * FROM parties"), [])

    def test_promote_requires_and_stores_both_flags(self):
        self.write_gh_fixture("view_acme-app_2", dict(OPEN_VIEW))
        self.start("adv-1", "fix typo", "--task", "demo-epic/T02")
        self.assertEqual(self.cli(["adventurer", "promote", "alpha", "--reason", "grew"], "adv-1")[0], 2)
        code, out, err = self.cli(["adventurer", "promote", "alpha", "--reason", "grew"] + GOAL, "adv-1")
        self.assertEqual(code, 0, err)
        party = self.party()
        self.assertEqual((party["goal"], party["done_when"]), ("ship the goal", "all merged"))


class SetTests(PartyGoalTestCase):
    def setUp(self):
        super().setUp()
        self.start_alpha()

    def test_set_one_field_keeps_the_other(self):
        code, out, err = self.cli(["party", "set", "alpha", "--goal", "new goal"], "sess-1")
        self.assertEqual(code, 0, err)
        party = self.party()
        self.assertEqual((party["goal"], party["done_when"]), ("new goal", "all merged"))
        self.assertEqual(self.cli(["party", "set", "alpha", "--done-when", "new done"], None)[0], 0)
        party = self.party()
        self.assertEqual((party["goal"], party["done_when"]), ("new goal", "new done"))

    def test_set_both_fields(self):
        self.assertEqual(self.cli(["party", "set", "alpha", "--goal", "a", "--done-when", "b"], None)[0], 0)
        party = self.party()
        self.assertEqual((party["goal"], party["done_when"]), ("a", "b"))

    def test_set_without_fields_is_refused(self):
        code, out, err = self.cli(["party", "set", "alpha"], None)
        self.assertEqual(code, 1)
        self.assertIn("needs --goal or --done-when", err)

    def test_blank_value_is_refused(self):
        self.assertEqual(self.cli(["party", "set", "alpha", "--goal", " "], None)[0], 1)
        self.assertEqual(self.party()["goal"], "ship the goal")

    def test_closed_or_unknown_party_is_refused(self):
        self.assertEqual(self.cli(["party", "set", "ghost", "--goal", "g"], None)[0], 1)
        self.cli(["party", "close", "--pending", "none"], "sess-1")
        code, out, err = self.cli(["party", "set", "alpha", "--goal", "g"], None)
        self.assertEqual(code, 1)
        self.assertIn("is closed", err)


class DisplayTests(PartyGoalTestCase):
    def setUp(self):
        super().setUp()
        self.start_alpha()

    def test_board_header_shows_goal_and_done_when(self):
        code, out, err = self.cli(["board"], None)
        self.assertIn("goal: ship the goal", out)
        self.assertIn("done when: all merged", out)
        self.assertNotIn("no goal", out)

    def test_board_shows_no_goal_for_an_old_party(self):
        conn = sqlite3.connect(str(paths.db_path()))
        conn.execute("UPDATE parties SET goal = NULL, done_when = NULL")
        conn.commit()
        conn.close()
        code, out, err = self.cli(["board"], None)
        self.assertIn("no goal", out)

    def test_revive_list_shows_goal(self):
        code, out, err = self.cli(["revive", "--list"], None)
        self.assertIn("goal: ship the goal", out)

    def test_brief_shows_goal_and_done_when(self):
        code, out, err = self.cli(["brief"], "sess-1")
        self.assertIn("goal: ship the goal", out)
        self.assertIn("done when: all merged", out)

    def test_handoff_file_has_a_goal_section(self):
        code, out, err = self.cli(["handoff", "--in-flight", "x", "--learned", "y"], "sess-1")
        self.assertEqual(code, 0, err)
        text = (paths.handoffs_dir() / "alpha-g1.md").read_text()
        self.assertIn("## Goal\ngoal: ship the goal\ndone when: all merged", text)


class TaskAddTests(PartyGoalTestCase):
    def setUp(self):
        super().setUp()
        self.start_alpha()
        self.cli(["quest", "add", "q1", "--title", "Q", "--no-epic"], "sess-1")

    def test_task_add_requires_a_reason_when_done_when_is_set(self):
        code, out, err = self.cli(["task", "add", "q1/T01", "--title", "t"], "sess-1")
        self.assertEqual(code, 1)
        self.assertIn("--reason must state how the task serves it", err)
        self.assertEqual(self.rows("SELECT * FROM quest_tasks"), [])

    def test_task_add_with_reason_is_accepted(self):
        code, out, err = self.cli(["task", "add", "q1/T01", "--title", "t", "--reason", "closes the goal"], "sess-1")
        self.assertEqual(code, 0, err)

    def test_task_add_without_done_when_needs_no_reason(self):
        conn = sqlite3.connect(str(paths.db_path()))
        conn.execute("UPDATE parties SET done_when = NULL")
        conn.commit()
        conn.close()
        self.assertEqual(self.cli(["task", "add", "q1/T01", "--title", "t"], "sess-1")[0], 0)


class ReplayTests(PartyGoalTestCase):
    def test_old_party_started_event_replays_with_null_goal(self):
        self.start_alpha()
        conn = sqlite3.connect(str(paths.db_path()))
        row = conn.execute("SELECT id, payload FROM events WHERE kind = 'party.started'").fetchone()
        payload = json.loads(row[1])
        del payload["goal"], payload["done_when"]
        conn.execute("UPDATE events SET payload = ? WHERE id = ?", (json.dumps(payload), row[0]))
        conn.commit()
        conn.close()
        code, out, err = self.cli(["rebuild"], None)
        self.assertEqual(code, 0, err)
        party = self.party()
        self.assertEqual((party["goal"], party["done_when"]), (None, None))
