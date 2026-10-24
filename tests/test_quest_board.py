import sqlite3

from guild import cli, db, paths, schema
from guild.commands import quest as quest_commands
from guild.errors import GuildError
from tests.mq_fixtures import TASKS_MD
from tests.testutil import GuildTestCase

_OLD_QUESTS = """
CREATE TABLE quests (
    slug TEXT PRIMARY KEY,
    project TEXT,
    party TEXT NOT NULL,
    epic TEXT,
    title TEXT NOT NULL,
    state TEXT NOT NULL
)
"""


class QuestBoardTestCase(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        code, out, err = self.sync_sdd(self.repo_dir, None, "acme", "demo-epic", TASKS_MD)
        self.assertEqual(code, 0, err)

    def cli(self, argv, session_id):
        return self.run_cli(argv, session_id, self.repo_dir)

    def ok(self, argv, session_id):
        code, out, err = self.cli(argv, session_id)
        self.assertEqual(code, 0, err)
        return out

    def rows(self, sql):
        conn = sqlite3.connect(str(paths.db_path()))
        conn.row_factory = sqlite3.Row
        self.addCleanup(conn.close)
        return conn.execute(sql).fetchall()

    def ctx(self):
        ctx = cli._build_context(None, self.repo_dir)
        self.addCleanup(ctx.conn.close)
        return ctx

    def open_quest(self, slug, tasks, session_id):
        return self.ok(
            ["quest", "add", slug, "--open", "--title", slug, "--epic", "demo-epic", "--tasks", tasks],
            session_id,
        )

    def start_party(self, name, session_id):
        self.ok(["party", "start", name, "--reason", "test reason"], session_id)


class OpenQuestSchemaTests(GuildTestCase):
    def test_not_null_party_is_relaxed_and_rows_are_kept(self):
        db_path = self.data_home / "guild.db"
        raw = sqlite3.connect(str(db_path))
        raw.execute(_OLD_QUESTS)
        raw.execute("INSERT INTO quests VALUES ('old', 'acme', 'alpha', NULL, 'Old', 'active')")
        raw.commit()
        raw.close()
        conn = db.connect(db_path)
        self.addCleanup(conn.close)
        party_column = [r for r in conn.execute("PRAGMA table_info(quests)") if r["name"] == "party"][0]
        self.assertEqual(party_column["notnull"], 0)
        self.assertEqual(conn.execute("SELECT party FROM quests WHERE slug = 'old'").fetchone()["party"], "alpha")
        schema.create_all(conn)
        conn.execute("INSERT INTO quests VALUES ('open', 'acme', NULL, NULL, 'Open', 'active')")


class OpenQuestAddTests(QuestBoardTestCase):
    def test_human_without_session_adds_an_open_quest(self):
        out = self.open_quest("pre", "T02,T03", None)
        self.assertIn("quest 'pre' added", out)
        row = self.rows("SELECT * FROM quests WHERE slug = 'pre'")[0]
        self.assertIsNone(row["party"])
        self.assertEqual(row["project"], "acme")
        self.assertEqual(len(self.rows("SELECT * FROM quest_tasks WHERE quest = 'pre'")), 2)

    def test_party_and_adventurer_add_open_quests(self):
        self.start_party("alpha", "sess-1")
        self.open_quest("by-party", "T02", "sess-1")
        self.ok(["adventurer", "start", "plan", "--reason", "test reason"], "adv-1")
        self.open_quest("by-adv", "T03", "adv-1")
        self.assertEqual(
            [r["slug"] for r in self.rows("SELECT slug FROM quests WHERE party IS NULL ORDER BY slug")],
            ["by-adv", "by-party"],
        )

    def test_no_epic_open_quest(self):
        self.ok(
            ["quest", "add", "free", "--open", "--title", "Free", "--no-epic", "--tasks", "a,b", "--titles", "A,B"],
            None,
        )
        self.assertEqual(len(self.rows("SELECT * FROM quest_tasks WHERE quest = 'free'")), 2)

    def test_taken_tasks_are_refused(self):
        self.open_quest("pre", "T02", None)
        code, out, err = self.cli(
            ["quest", "add", "dup", "--open", "--title", "d", "--epic", "demo-epic", "--tasks", "T02"], None
        )
        self.assertEqual(code, 1)
        self.assertIn("in open quest pre", err)
        self.start_party("alpha", "sess-1")
        code, out, err = self.cli(
            ["quest", "add", "mine", "--title", "m", "--epic", "demo-epic", "--tasks", "T02"], "sess-1"
        )
        self.assertEqual(code, 1)
        self.assertIn("in open quest pre", err)

    def test_open_refuses_followups_unsynced_epic_and_held_task(self):
        self.start_party("alpha", "sess-1")
        code, out, err = self.cli(
            ["quest", "add", "x", "--open", "--title", "x", "--followups-of", "y", "--tasks", "a"], None
        )
        self.assertEqual(code, 1)
        self.assertIn("--open", err)
        code, out, err = self.cli(
            ["quest", "add", "x", "--open", "--title", "x", "--epic", "nope", "--tasks", "T01"], None
        )
        self.assertEqual(code, 1)
        self.ok(["adventurer", "start", "job", "--task", "demo-epic/T03", "--reason", "test reason"], "adv-1")
        code, out, err = self.cli(
            ["quest", "add", "x", "--open", "--title", "x", "--epic", "demo-epic", "--tasks", "T03"], None
        )
        self.assertEqual(code, 1)
        self.assertIn("held by adventurer 1", err)

    def test_plain_add_still_needs_a_binding(self):
        code, out, err = self.cli(["quest", "add", "x", "--title", "x", "--epic", "demo-epic"], None)
        self.assertEqual(code, 1)

    def test_task_add_and_claim_refuse_open_quest_tasks(self):
        self.open_quest("pre", "T02", None)
        self.start_party("alpha", "sess-1")
        self.ok(["quest", "add", "mine", "--title", "m", "--epic", "demo-epic"], "sess-1")
        code, out, err = self.cli(["task", "add", "mine/T02", "--title", "t"], "sess-1")
        self.assertEqual(code, 1)
        self.assertIn("in open quest pre", err)
        code, out, err = self.cli(["claim", "task:demo-epic/T02", "--ttl", "1h"], "sess-1")
        self.assertEqual(code, 1)
        self.assertIn("open quest pre", err)
        code, out, err = self.cli(["task", "add", "pre/T09", "--title", "t"], "sess-1")
        self.assertEqual(code, 1)
        self.assertIn("open", err)


class TakeReleaseTests(QuestBoardTestCase):
    def test_party_takes_and_owns_the_quest(self):
        self.open_quest("pre", "T02,T03", None)
        self.start_party("alpha", "sess-1")
        out = self.ok(["quest", "take", "pre"], "sess-1")
        self.assertIn("quest 'pre' taken", out)
        self.assertEqual(self.rows("SELECT party FROM quests WHERE slug = 'pre'")[0]["party"], "alpha")
        self.ok(["task", "start", "pre/T02"], "sess-1")
        code, out, err = self.cli(["quest", "take", "pre"], "sess-1")
        self.assertEqual(code, 1)

    def test_take_refusals(self):
        self.open_quest("pre", "T02", None)
        self.assertEqual(self.cli(["quest", "take", "pre"], None)[0], 1)
        self.ok(["adventurer", "start", "job", "--reason", "test reason"], "adv-1")
        code, out, err = self.cli(["quest", "take", "pre"], "adv-1")
        self.assertEqual(code, 1)
        self.start_party("alpha", "sess-1")
        self.assertEqual(self.cli(["quest", "take", "nope"], "sess-1")[0], 1)
        other = self.register_project("beta", ["acme/other"])
        self.sync_sdd(other, None, "beta", "other-epic", TASKS_MD)
        code, out, err = self.run_cli(
            ["quest", "add", "far", "--open", "--title", "f", "--epic", "other-epic", "--tasks", "T02"], None, other
        )
        self.assertEqual(code, 0, err)
        code, out, err = self.cli(["quest", "take", "far"], "sess-1")
        self.assertEqual(code, 1)
        self.assertIn("project", err)

    def test_held_task_stays_and_is_skipped_until_adventurer_done(self):
        self.open_quest("pre", "T02,T03", None)
        self.ok(["adventurer", "start", "job", "--task", "demo-epic/T02", "--reason", "test reason"], "adv-1")
        self.assertEqual(self.rows("SELECT quest FROM quest_tasks WHERE tid = 'T02'")[0]["quest"], "pre")
        self.start_party("alpha", "sess-1")
        self.ok(["quest", "take", "pre"], "sess-1")
        out = self.ok(["next"], "sess-1")
        self.assertIn("pre/T03", out)
        code, out, err = self.cli(["task", "start", "pre/T02"], "sess-1")
        self.assertEqual(code, 1)
        self.assertIn("held by adventurer 1", err)
        self.ok(["adventurer", "done", "--pending", "none"], "adv-1")
        self.ok(["task", "start", "pre/T02"], "sess-1")

    def test_adventurer_start_on_open_no_epic_task(self):
        self.ok(
            ["quest", "add", "free", "--open", "--title", "F", "--no-epic", "--tasks", "a,b", "--titles", "A,B"],
            None,
        )
        self.ok(["adventurer", "start", "job", "--task", "free/a", "--reason", "test reason"], "adv-1")
        code, out, err = self.cli(["adventurer", "start", "job2", "--task", "free/a", "--reason", "test reason"], "adv-2")
        self.assertEqual(code, 1)
        self.assertIn("held by adventurer 1", err)
        self.assertEqual(self.cli(["adventurer", "start", "job2", "--task", "free/zz", "--reason", "test reason"], "adv-2")[0], 1)

    def test_release_returns_untouched_quest(self):
        self.open_quest("pre", "T02", None)
        self.start_party("alpha", "sess-1")
        self.ok(["quest", "take", "pre"], "sess-1")
        self.start_party("beta", "sess-2")
        code, out, err = self.cli(["quest", "release", "pre"], "sess-2")
        self.assertEqual(code, 1)
        out = self.ok(["quest", "release", "pre"], "sess-1")
        self.assertIn("quest 'pre' released", out)
        self.assertIsNone(self.rows("SELECT party FROM quests WHERE slug = 'pre'")[0]["party"])
        code, out, err = self.cli(["quest", "release", "pre"], "sess-1")
        self.assertEqual(code, 1)

    def test_release_refuses_started_work_open_pr_and_claim(self):
        self.open_quest("pre", "T02,T03", None)
        self.start_party("alpha", "sess-1")
        self.ok(["quest", "take", "pre"], "sess-1")
        self.ok(["task", "start", "pre/T02"], "sess-1")
        code, out, err = self.cli(["quest", "release", "pre"], "sess-1")
        self.assertEqual(code, 1)
        self.assertIn("T02", err)
        self.open_quest("pre2", "T01", None)
        self.ok(["quest", "take", "pre2"], "sess-1")
        self.ok(["claim", "task:demo-epic/T01", "--ttl", "1h"], "sess-1")
        code, out, err = self.cli(["quest", "release", "pre2"], "sess-1")
        self.assertEqual(code, 1)
        self.assertIn("claim", err)

    def test_release_refuses_open_pr(self):
        self.open_quest("pre", "T02", None)
        self.start_party("alpha", "sess-1")
        self.ok(["quest", "take", "pre"], "sess-1")
        self.write_gh_fixture(
            "view_acme-app_1",
            {"state": "OPEN", "isDraft": True, "headRefName": "f", "title": "t", "statusCheckRollup": []},
        )
        self.ok(["pr", "track", "acme/app#1", "--task", "pre/T02", "--what", "x", "--waits", "y"], "sess-1")
        code, out, err = self.cli(["quest", "release", "pre"], "sess-1")
        self.assertEqual(code, 1)
        self.assertIn("PR", err)

    def test_for_party_and_for_owner_functions(self):
        self.open_quest("pre", "T02", None)
        self.start_party("alpha", "sess-1")
        ctx = self.ctx()
        with self.assertRaises(GuildError):
            quest_commands.take_for_party(ctx, "pre", "ghost")
        with self.assertRaises(GuildError):
            quest_commands.release_for_owner(ctx, "pre")
        self.assertIn("taken", quest_commands.take_for_party(ctx, "pre", "alpha"))
        with self.assertRaises(GuildError):
            quest_commands.take_for_party(ctx, "pre", "alpha")
        self.assertIn("released", quest_commands.release_for_owner(ctx, "pre"))
        self.assertEqual(self.rows("SELECT COUNT(*) AS n FROM events WHERE kind = 'quest.taken'")[0]["n"], 1)

    def test_take_for_party_refuses_other_project_and_closed_party(self):
        other = self.register_project("beta", ["acme/other"])
        self.run_cli(["party", "start", "gamma", "--reason", "test reason"], "sess-9", other)
        self.open_quest("pre", "T02", None)
        with self.assertRaises(GuildError):
            quest_commands.take_for_party(self.ctx(), "pre", "gamma")

    def test_state_survives_rebuild(self):
        self.open_quest("pre", "T02", None)
        self.open_quest("pre2", "T03", None)
        self.start_party("alpha", "sess-1")
        self.ok(["quest", "take", "pre"], "sess-1")
        self.ok(["quest", "take", "pre2"], "sess-1")
        self.ok(["quest", "release", "pre2"], "sess-1")
        self.ok(["rebuild"], None)
        parties = {r["slug"]: r["party"] for r in self.rows("SELECT slug, party FROM quests")}
        self.assertEqual(parties, {"pre": "alpha", "pre2": None})


class QuestBoardCommandTests(QuestBoardTestCase):
    def test_board_lists_open_quests_and_free_tasks(self):
        self.open_quest("pre", "T02", None)
        self.ok(["adventurer", "start", "job", "--task", "demo-epic/T02", "--reason", "test reason"], "adv-1")
        self.start_party("alpha", "sess-1")
        self.ok(["quest", "add", "mine", "--title", "m", "--epic", "demo-epic", "--tasks", "T03"], "sess-1")
        out = self.ok(["quest", "board"], None)
        self.assertIn("project acme", out)
        self.assertIn("pre", out)
        self.assertIn("held by adventurer 1", out)
        free = out.split("demo-epic")[-1]
        self.assertIn("T01", free)
        self.assertNotIn("T02", free)
        self.assertNotIn("T03", free)

    def test_board_hides_claimed_and_held_and_done_epics(self):
        self.start_party("alpha", "sess-1")
        self.ok(["claim", "task:demo-epic/T01", "--ttl", "1h"], "sess-1")
        self.ok(["adventurer", "start", "job", "--task", "demo-epic/T02", "--reason", "test reason"], "adv-1")
        out = self.ok(["quest", "board", "--project", "acme"], None)
        self.assertNotIn("T01", out)
        self.assertNotIn("T02", out)
        self.assertIn("T03", out)

    def test_board_unknown_project_fails(self):
        self.assertEqual(self.cli(["quest", "board", "--project", "nope"], None)[0], 1)

    def test_next_offers_open_quest_only_without_queued_work(self):
        self.open_quest("old", "T02", None)
        self.open_quest("new", "T03", None)
        self.start_party("alpha", "sess-1")
        self.assertIn("take open quest old", self.ok(["next"], "sess-1"))
        self.ok(["quest", "take", "old"], "sess-1")
        out = self.ok(["next"], "sess-1")
        self.assertIn("old/T02", out)
        self.assertNotIn("take open quest", out)
        self.ok(["task", "start", "old/T02"], "sess-1")
        self.ok(["task", "done", "old/T02"], "sess-1")
        self.assertIn("take open quest new", self.ok(["next", "--all"], "sess-1"))

    def test_next_nothing_without_open_quests(self):
        self.start_party("alpha", "sess-1")
        self.assertIn("nothing actionable", self.ok(["next"], "sess-1"))


class OpenQuestReadersTests(QuestBoardTestCase):
    def test_readers_survive_an_open_quest(self):
        self.open_quest("pre", "T02", None)
        self.start_party("alpha", "sess-1")
        for argv in (
            ["board"],
            ["drift"],
            ["drift", "--all"],
            ["drift", "--epic", "demo-epic"],
            ["merge-queue"],
            ["brief"],
            ["history"],
            ["inbox"],
        ):
            code, out, err = self.cli(argv, "sess-1")
            self.assertEqual(code, 0, "{}: {}".format(argv, err))
        out = self.ok(["board"], None)
        self.assertNotIn("None", out)
        out = self.ok(["drift"], None)
        self.assertNotIn("without party", out)
