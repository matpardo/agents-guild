import json

from guild import context, db, paths, timeutil
from guild.commands import board as board_commands
from tests.mq_fixtures import OPEN_VIEW
from tests.test_adventurer import AdventurerTestCase


class ReasonOnStartTests(AdventurerTestCase):
    def test_reason_flag_is_required_on_both_starts(self):
        self.assertEqual(self.cli(["party", "start", "alpha"], "sess-1")[0], 2)
        self.assertEqual(self.cli(["adventurer", "start", "fix typo"], "adv-1")[0], 2)

    def test_empty_or_sensitive_reason_is_refused(self):
        self.assertEqual(self.cli(["party", "start", "alpha", "--reason", "  "], "sess-1")[0], 1)
        self.assertEqual(self.cli(["party", "start", "alpha", "--reason", "mail me@x.com"], "sess-1")[0], 1)
        self.assertEqual(
            self.cli(["adventurer", "start", "x", "--task", "demo-epic/T90", "--reason", "  "], "adv-1")[0], 1
        )
        self.assertEqual(self.rows("SELECT * FROM parties"), [])
        self.assertEqual(self.rows("SELECT * FROM adventurers"), [])

    def test_reason_is_stored_for_party_and_adventurer(self):
        self.cli(["party", "start", "alpha", "--reason", "several PRs"], "sess-1")
        self.cli(["adventurer", "start", "fix typo", "--task", "demo-epic/T90", "--reason", "one PR job"], "adv-1")
        party = self.rows("SELECT reason, from_adventurer FROM parties")[0]
        self.assertEqual((party["reason"], party["from_adventurer"]), ("several PRs", None))
        self.assertEqual(self.rows("SELECT reason FROM adventurers")[0]["reason"], "one PR job")
        code, out, err = self.cli(["adventurers", "1"], None)
        self.assertIn("reason: one PR job", out)

    def test_old_event_without_reason_projects_null(self):
        self.cli(["party", "start", "alpha", "--reason", "r"], "sess-1")
        conn = db.connect(paths.db_path())
        self.addCleanup(conn.close)
        payload = json.loads(conn.execute("SELECT payload FROM events WHERE kind = 'party.started'").fetchone()[0])
        self.assertEqual(payload["reason"], "r")
        self.assertIsNone(payload["from_adventurer"])


class PromoteTests(AdventurerTestCase):
    def setUp(self):
        super().setUp()
        self.write_gh_fixture("view_acme-app_2", dict(OPEN_VIEW))
        self.start("adv-1", "fix typo", "--task", "demo-epic/T02")
        self.cli(["pr", "track", "acme/app#2", "--task", "demo-epic/T02", "--what", "typo", "--waits", "r"], "adv-1")

    def test_promote_turns_the_adventurer_into_a_party_leader(self):
        code, out, err = self.cli(["adventurer", "promote", "alpha", "--reason", "grew to several PRs"], "adv-1")
        self.assertEqual(code, 0, err)
        self.assertIn("adventurer 1 promoted to party 'alpha'", out)
        self.assertIn("demo-epic/T02", out)
        adventurer = self.rows("SELECT state, pending FROM adventurers")[0]
        self.assertEqual((adventurer["state"], adventurer["pending"]), ("promoted", "promoted to party alpha"))
        party = self.rows("SELECT reason, from_adventurer, generation, leader_session_id FROM parties")[0]
        self.assertEqual(
            (party["reason"], party["from_adventurer"], party["generation"], party["leader_session_id"]),
            ("grew to several PRs", 1, 1, "adv-1"),
        )
        pr = self.rows("SELECT party, adventurer FROM prs WHERE number = 2")[0]
        self.assertEqual((pr["party"], pr["adventurer"]), ("alpha", 1))
        self.assertEqual(self.rows("SELECT COUNT(*) AS n FROM leaders WHERE party = 'alpha'")[0]["n"], 1)
        self.assertEqual(self.cli(["quest", "add", "q", "--title", "Q", "--no-epic"], "adv-1")[0], 0)

    def test_promote_without_task_prints_no_task_hint(self):
        self.cli(["adventurer", "done", "--pending", "none"], "adv-1")
        self.start_health_job("adv-2")
        code, out, err = self.cli(["adventurer", "promote", "beta", "--reason", "grew"], "adv-2")
        self.assertEqual(code, 0, err)
        self.assertNotIn("add task", out)

    def test_promote_refusals(self):
        self.assertEqual(self.cli(["adventurer", "promote", "alpha", "--reason", "r"], "sess-9")[0], 1)
        self.cli(["party", "start", "taken", "--reason", "r"], "sess-1")
        self.assertEqual(self.cli(["adventurer", "promote", "alpha", "--reason", "r"], "sess-1")[0], 1)
        code, out, err = self.cli(["adventurer", "promote", "taken", "--reason", "r"], "adv-1")
        self.assertEqual(code, 1)
        self.assertIn("already exists", err)
        self.assertEqual(self.cli(["adventurer", "promote", "alpha", "--reason", " "], "adv-1")[0], 1)
        self.assertEqual(self.cli(["adventurer", "promote", "alpha"], "adv-1")[0], 2)
        self.assertEqual(self.rows("SELECT state FROM adventurers")[0]["state"], "active")

    def test_board_shows_origin_and_drops_the_promoted_adventurer(self):
        self.cli(["adventurer", "promote", "alpha", "--reason", "grew"], "adv-1")
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
        model = board_commands.board_model(ctx)
        self.assertEqual(model["adventurers"], [])
        party = model["parties"][0]
        self.assertEqual((party["reason"], party["from_adventurer"]), ("grew", 1))
        self.assertRegex(party["dates"], r"^created \d{4}-\d{2}-\d{2} \d{2}:\d{2}$")
        code, out, err = self.cli(["board"], None)
        self.assertIn("reason: grew", out)


class AdventurerBoardReasonTests(AdventurerTestCase):
    def test_active_adventurer_shows_reason_and_start(self):
        self.start("adv-1", "fix typo", "--task", "demo-epic/T90")
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
        entry = board_commands.board_model(ctx)["adventurers"][0]
        self.assertEqual(entry["reason"], "test reason")
        self.assertRegex(entry["dates"], r"^created \d{4}-\d{2}-\d{2} \d{2}:\d{2}$")
        code, out, err = self.cli(["board"], None)
        self.assertIn("reason: test reason", out)


class AddReasonTests(AdventurerTestCase):
    def setUp(self):
        super().setUp()
        self.cli(["party", "start", "alpha", "--reason", "r"], "sess-1")

    def _payloads(self, kind):
        return [
            json.loads(row["payload"]) for row in self.rows("SELECT payload FROM events WHERE kind = '{}'".format(kind))
        ]

    def test_quest_and_task_add_record_reason_only_when_given(self):
        self.cli(["quest", "add", "q1", "--title", "Q", "--no-epic", "--reason", "found on the fly"], "sess-1")
        self.cli(["quest", "add", "q2", "--title", "Q", "--no-epic"], "sess-1")
        self.cli(["task", "add", "q1/T01", "--title", "t", "--reason", "needed"], "sess-1")
        self.cli(["task", "add", "q1/T02", "--title", "t"], "sess-1")
        quests = self._payloads("quest.added")
        self.assertEqual(quests[0]["reason"], "found on the fly")
        self.assertNotIn("reason", quests[1])
        tasks = self._payloads("task.added")
        self.assertEqual(tasks[0]["reason"], "needed")
        self.assertNotIn("reason", tasks[1])

    def test_invalid_reason_is_refused(self):
        self.assertEqual(self.cli(["quest", "add", "q1", "--title", "Q", "--no-epic", "--reason", " "], "sess-1")[0], 1)
        self.cli(["quest", "add", "q1", "--title", "Q", "--no-epic"], "sess-1")
        self.assertEqual(self.cli(["task", "add", "q1/T01", "--title", "t", "--reason", "me@x.com"], "sess-1")[0], 1)
