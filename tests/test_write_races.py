import contextlib
import sqlite3
from datetime import timedelta
from unittest import mock

from guild import db, paths, timeutil
from tests.mq_fixtures import TASKS_MD
from tests.testutil import GuildTestCase


@contextlib.contextmanager
def competing_write_before_transaction(competitor):
    real_writing = db.writing
    pending = [competitor]

    @contextlib.contextmanager
    def racing_writing(conn):
        while pending:
            pending.pop()()
        with real_writing(conn) as inner:
            yield inner

    with mock.patch("guild.db.writing", racing_writing):
        yield


class WriteRaceCase(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.cli("sess-1", ["party", "start", "alpha", "--reason", "test reason"])
        self.cli("sess-2", ["party", "start", "beta", "--reason", "test reason"])

    def cli(self, session_id, argv):
        return self.run_cli(argv, session_id, self.repo_dir)

    def human_cli(self, argv):
        return self.run_cli(argv, None, None)

    def rows(self, sql):
        conn = sqlite3.connect(str(paths.db_path()))
        self.addCleanup(conn.close)
        return [tuple(row) for row in conn.execute(sql).fetchall()]

    def add_open_quest(self, slug, tids):
        code, out, err = self.cli(
            "sess-1",
            ["quest", "add", slug, "--open", "--no-epic", "--title", "Demo", "--tasks", tids, "--titles", tids],
        )
        self.assertEqual(code, 0, err)

    def add_quest(self, session_id, slug, tids):
        code, out, err = self.cli(
            session_id, ["quest", "add", slug, "--no-epic", "--title", "Demo", "--tasks", tids, "--titles", tids]
        )
        self.assertEqual(code, 0, err)


class ClaimRaceTests(WriteRaceCase):
    def test_claim_refused_when_other_party_claims_first(self):
        with competing_write_before_transaction(lambda: self.cli("sess-2", ["claim", "ci.yml", "--ttl", "30m"])):
            code, out, err = self.cli("sess-1", ["claim", "ci.yml", "--ttl", "30m"])
        self.assertEqual(code, 1)
        self.assertIn("claimed by party 'beta'", err)
        self.assertEqual(self.rows("SELECT party FROM claims WHERE area = 'ci.yml'"), [("beta",)])

    def test_task_claim_refused_when_adventurer_starts_first(self):
        code, out, err = self.sync_sdd(self.repo_dir, None, "acme", "demo-epic", TASKS_MD)
        self.assertEqual(code, 0, err)
        with competing_write_before_transaction(
            lambda: self.cli(
                "adv-1", ["adventurer", "start", "fix", "--reason", "test reason", "--task", "demo-epic/T02"]
            )
        ):
            code, out, err = self.cli("sess-1", ["claim", "task:demo-epic/T02", "--ttl", "30m"])
        self.assertEqual(code, 1)
        self.assertIn("held by adventurer 1", err)
        self.assertEqual(self.rows("SELECT area FROM claims"), [])

    def test_release_refused_when_other_party_claimed_the_expired_area_first(self):
        self.cli("sess-1", ["claim", "ci.yml", "--ttl", "30m"])

        def beta_claims_after_expiry():
            with mock.patch("guild.timeutil.utcnow", return_value=timeutil.utcnow() + timedelta(hours=1)):
                self.cli("sess-2", ["claim", "ci.yml", "--ttl", "30m"])

        with competing_write_before_transaction(beta_claims_after_expiry):
            code, out, err = self.cli("sess-1", ["release", "ci.yml"])
        self.assertEqual(code, 1)
        self.assertIn("does not hold claim", err)
        self.assertEqual(self.rows("SELECT party FROM claims WHERE area = 'ci.yml'"), [("beta",)])


class QuestTakeRaceTests(WriteRaceCase):
    def test_take_refused_when_other_party_takes_first(self):
        self.add_open_quest("demo", "T01")
        with competing_write_before_transaction(lambda: self.cli("sess-2", ["quest", "take", "demo"])):
            code, out, err = self.cli("sess-1", ["quest", "take", "demo"])
        self.assertEqual(code, 1)
        self.assertIn("is not open", err)
        self.assertEqual(self.rows("SELECT party FROM quests WHERE slug = 'demo'"), [("beta",)])
        self.assertEqual(self.rows("SELECT COUNT(*) FROM events WHERE kind = 'quest.taken'"), [(1,)])


class AdventurerStartRaceTests(WriteRaceCase):
    def test_start_refused_when_party_takes_the_task_first(self):
        self.add_open_quest("demo", "T01")
        with competing_write_before_transaction(lambda: self.cli("sess-2", ["quest", "take", "demo"])):
            code, out, err = self.cli(
                "adv-1", ["adventurer", "start", "fix", "--reason", "test reason", "--task", "demo/T01"]
            )
        self.assertEqual(code, 1)
        self.assertIn("demo", err)
        self.assertEqual(self.rows("SELECT id FROM adventurers"), [])


class TaskStateRaceTests(WriteRaceCase):
    def setUp(self):
        super().setUp()
        self.add_quest("sess-1", "demo", "T01")

    def test_start_refused_when_task_done_first(self):
        with competing_write_before_transaction(lambda: self.cli("sess-1", ["task", "done", "demo/T01"])):
            code, out, err = self.cli("sess-1", ["task", "start", "demo/T01"])
        self.assertEqual(code, 1)
        self.assertIn("already done", err)
        self.assertEqual(self.rows("SELECT state FROM quest_tasks WHERE quest = 'demo'"), [("done",)])

    def test_block_refused_when_task_done_first(self):
        with competing_write_before_transaction(lambda: self.cli("sess-1", ["task", "done", "demo/T01"])):
            code, out, err = self.cli("sess-1", ["task", "block", "demo/T01", "--reason", "stuck"])
        self.assertEqual(code, 1)
        self.assertIn("already done", err)
        self.assertEqual(self.rows("SELECT state FROM quest_tasks WHERE quest = 'demo'"), [("done",)])

    def test_done_recorded_once_when_task_done_first(self):
        with competing_write_before_transaction(lambda: self.cli("sess-1", ["task", "done", "demo/T01"])):
            code, out, err = self.cli("sess-1", ["task", "done", "demo/T01"])
        self.assertEqual(code, 1)
        self.assertIn("already done", err)
        self.assertEqual(self.rows("SELECT COUNT(*) FROM events WHERE kind = 'task.done'"), [(1,)])


class QuestAddRaceTests(WriteRaceCase):
    def setUp(self):
        super().setUp()
        code, out, err = self.sync_sdd(self.repo_dir, None, "acme", "demo-epic", TASKS_MD)
        self.assertEqual(code, 0, err)

    def test_add_refused_when_other_party_claims_the_task_first(self):
        with competing_write_before_transaction(
            lambda: self.cli("sess-2", ["claim", "task:demo-epic/T02", "--ttl", "30m"])
        ):
            code, out, err = self.cli(
                "sess-1", ["quest", "add", "wave", "--title", "Wave", "--epic", "demo-epic", "--tasks", "T02"]
            )
        self.assertEqual(code, 1)
        self.assertIn("claimed by party beta", err)
        self.assertEqual(self.rows("SELECT slug FROM quests"), [])

    def test_add_open_refused_when_other_party_quest_takes_the_task_first(self):
        with competing_write_before_transaction(
            lambda: self.cli(
                "sess-2", ["quest", "add", "beta-wave", "--title", "Wave", "--epic", "demo-epic", "--tasks", "T02"]
            )
        ):
            code, out, err = self.cli(
                "sess-1",
                ["quest", "add", "open-wave", "--open", "--title", "Wave", "--epic", "demo-epic", "--tasks", "T02"],
            )
        self.assertEqual(code, 1)
        self.assertIn("T02 is in quest beta-wave of party beta", err)
        self.assertEqual(self.rows("SELECT slug FROM quests"), [("beta-wave",)])


class TaskAddRaceTests(WriteRaceCase):
    def test_add_refused_when_other_party_claims_the_task_first(self):
        code, out, err = self.sync_sdd(self.repo_dir, None, "acme", "demo-epic", TASKS_MD)
        self.assertEqual(code, 0, err)
        code, out, err = self.cli(
            "sess-1", ["quest", "add", "wave", "--title", "Wave", "--epic", "demo-epic", "--tasks", "T01"]
        )
        self.assertEqual(code, 0, err)
        with competing_write_before_transaction(
            lambda: self.cli("sess-2", ["claim", "task:demo-epic/T02", "--ttl", "30m"])
        ):
            code, out, err = self.cli("sess-1", ["task", "add", "wave/T02", "--title", "Second"])
        self.assertEqual(code, 1)
        self.assertIn("claimed by party beta", err)
        self.assertEqual(self.rows("SELECT tid FROM quest_tasks WHERE quest = 'wave'"), [("T01",)])


class TaskMoveRaceTests(WriteRaceCase):
    def test_move_refused_when_task_started_first(self):
        code, out, err = self.sync_sdd(self.repo_dir, None, "acme", "demo-epic", TASKS_MD)
        self.assertEqual(code, 0, err)
        self.cli("sess-1", ["quest", "add", "src", "--title", "Src", "--epic", "demo-epic", "--tasks", "T02,T03"])
        self.cli("sess-2", ["quest", "add", "dst", "--title", "Dst", "--epic", "demo-epic"])
        with competing_write_before_transaction(lambda: self.cli("sess-1", ["task", "start", "src/T02"])):
            code, out, err = self.cli("sess-1", ["task", "move", "src/T02", "--to", "dst"])
        self.assertEqual(code, 1)
        self.assertIn("only queued or blocked tasks move", err)
        self.assertEqual(self.rows("SELECT quest FROM quest_tasks WHERE tid = 'T02'"), [("src",)])


class AskRaceTests(WriteRaceCase):
    def setUp(self):
        super().setUp()
        self.add_quest("sess-1", "demo", "T01")
        code, out, err = self.cli("sess-1", ["ask", "ready?", "--context", "x", "--ref", "task:demo/T01"])
        self.assertEqual(code, 0, err)

    def test_answer_refused_when_answered_first(self):
        with competing_write_before_transaction(lambda: self.human_cli(["answer", "1", "first"])):
            code, out, err = self.human_cli(["answer", "1", "second"])
        self.assertEqual(code, 1)
        self.assertIn("not open", err)
        self.assertEqual(self.rows("SELECT answer FROM asks WHERE id = 1"), [("first",)])

    def test_answer_refused_when_dismissed_first(self):
        with competing_write_before_transaction(lambda: self.human_cli(["dismiss", "1"])):
            code, out, err = self.human_cli(["answer", "1", "late"])
        self.assertEqual(code, 1)
        self.assertIn("not open", err)
        self.assertEqual(self.rows("SELECT state FROM asks WHERE id = 1"), [("dismissed",)])

    def test_dismiss_refused_when_answered_first(self):
        with competing_write_before_transaction(lambda: self.human_cli(["answer", "1", "first"])):
            code, out, err = self.human_cli(["dismiss", "1"])
        self.assertEqual(code, 1)
        self.assertIn("not open", err)
        self.assertEqual(self.rows("SELECT state FROM asks WHERE id = 1"), [("answered",)])


class QuestDoneRaceTests(WriteRaceCase):
    def test_done_refused_when_task_added_first(self):
        self.add_quest("sess-1", "demo", "T01")
        self.cli("sess-1", ["task", "done", "demo/T01"])
        with competing_write_before_transaction(
            lambda: self.cli("sess-1", ["task", "add", "demo/T02", "--title", "Second"])
        ):
            code, out, err = self.cli("sess-1", ["quest", "done", "demo"])
        self.assertEqual(code, 1)
        self.assertIn("T02 (queued)", err)
        self.assertEqual(self.rows("SELECT state FROM quests WHERE slug = 'demo'"), [("active",)])

    def test_done_recorded_once_when_done_first(self):
        self.add_quest("sess-1", "demo", "T01")
        self.cli("sess-1", ["task", "done", "demo/T01"])
        with competing_write_before_transaction(lambda: self.cli("sess-1", ["quest", "done", "demo"])):
            code, out, err = self.cli("sess-1", ["quest", "done", "demo"])
        self.assertEqual(code, 1)
        self.assertIn("already done", err)
        self.assertEqual(self.rows("SELECT COUNT(*) FROM events WHERE kind = 'quest.done'"), [(1,)])


class PartyResumeRaceTests(WriteRaceCase):
    def test_resume_refused_when_party_closed_first(self):
        with competing_write_before_transaction(
            lambda: self.human_cli(["party", "close", "alpha", "--pending", "none"])
        ):
            code, out, err = self.cli("sess-4", ["party", "resume", "alpha"])
        self.assertEqual(code, 1)
        self.assertIn("is closed", err)
        self.assertEqual(self.rows("SELECT state FROM parties WHERE name = 'alpha'"), [("closed",)])

    def test_second_resume_refused_and_first_stays_leader(self):
        with competing_write_before_transaction(lambda: self.cli("sess-3", ["party", "resume", "alpha"])):
            code, out, err = self.cli("sess-4", ["party", "resume", "alpha"])
        self.assertEqual(code, 1)
        self.assertIn("resumed by another session", err)
        self.assertEqual(self.rows("SELECT generation FROM parties WHERE name = 'alpha'"), [(2,)])
        self.assertEqual(
            self.rows("SELECT session_id FROM leaders WHERE party = 'alpha' AND generation = 2"), [("sess-3",)]
        )


class QuestReleaseRaceTests(WriteRaceCase):
    def test_release_refused_when_task_started_first(self):
        self.add_quest("sess-1", "demo", "T01")
        with competing_write_before_transaction(lambda: self.cli("sess-1", ["task", "start", "demo/T01"])):
            code, out, err = self.cli("sess-1", ["quest", "release", "demo"])
        self.assertEqual(code, 1)
        self.assertIn("T01 is active", err)
        self.assertEqual(self.rows("SELECT COUNT(*) FROM events WHERE kind = 'quest.released'"), [(0,)])

    def test_release_recorded_once_when_released_first(self):
        self.add_quest("sess-1", "demo", "T01")
        with competing_write_before_transaction(lambda: self.cli("sess-1", ["quest", "release", "demo"])):
            code, out, err = self.cli("sess-1", ["quest", "release", "demo"])
        self.assertEqual(code, 1)
        self.assertIn("already open", err)
        self.assertEqual(self.rows("SELECT COUNT(*) FROM events WHERE kind = 'quest.released'"), [(1,)])


class QuestIncompleteRaceTests(WriteRaceCase):
    def test_incomplete_recorded_once_when_marked_first(self):
        self.add_quest("sess-1", "demo", "T01")
        self.cli("sess-1", ["task", "done", "demo/T01"])
        self.cli("sess-1", ["quest", "done", "demo"])
        with competing_write_before_transaction(
            lambda: self.cli("sess-1", ["quest", "incomplete", "demo", "--reason", "first"])
        ):
            code, out, err = self.cli("sess-1", ["quest", "incomplete", "demo", "--reason", "second"])
        self.assertEqual(code, 1)
        self.assertIn("already marked incomplete", err)
        self.assertEqual(self.rows("SELECT COUNT(*) FROM events WHERE kind = 'quest.marked_incomplete'"), [(1,)])


class AdventurerRaceTests(WriteRaceCase):
    def setUp(self):
        super().setUp()
        self.add_open_quest("jobs", "T01")
        code, out, err = self.cli(
            "adv-1", ["adventurer", "start", "fix", "--reason", "test reason", "--task", "jobs/T01"]
        )
        self.assertEqual(code, 0, err)

    def test_done_recorded_once_when_done_first(self):
        with competing_write_before_transaction(lambda: self.cli("adv-1", ["adventurer", "done", "--pending", "none"])):
            code, out, err = self.cli("adv-1", ["adventurer", "done", "--pending", "none"])
        self.assertEqual(code, 1)
        self.assertIn("not an active adventurer", err)
        self.assertEqual(self.rows("SELECT COUNT(*) FROM events WHERE kind = 'adventurer.done'"), [(1,)])

    def test_dismiss_recorded_once_when_dismissed_first(self):
        self.cli("adv-1", ["adventurer", "done", "--pending", "none"])
        with competing_write_before_transaction(lambda: self.human_cli(["adventurer", "dismiss", "1"])):
            code, out, err = self.human_cli(["adventurer", "dismiss", "1"])
        self.assertEqual(code, 1)
        self.assertIn("not done", err)
        self.assertEqual(self.rows("SELECT COUNT(*) FROM events WHERE kind = 'adventurer.dismissed'"), [(1,)])


if __name__ == "__main__":
    import unittest

    unittest.main()
