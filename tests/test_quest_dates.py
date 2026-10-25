import sqlite3
from datetime import datetime, timedelta, timezone
from unittest import mock

from guild import db, paths
from guild.commands import quest_board
from tests.test_quest_board import QuestBoardTestCase

_T0 = datetime(2026, 10, 24, 9, 0, tzinfo=timezone.utc)


class QuestDatesTests(QuestBoardTestCase):
    def at(self, minutes, argv, session_id):
        with mock.patch("guild.timeutil.utcnow", return_value=_T0 + timedelta(minutes=minutes)):
            return self.ok(argv, session_id)

    def stamps(self):
        quest = self.rows("SELECT slug, created_at, updated_at FROM quests ORDER BY slug")
        task = self.rows("SELECT quest, tid, created_at, updated_at FROM quest_tasks ORDER BY quest, tid")
        return [tuple(row) for row in quest], [tuple(row) for row in task]

    def quest_row(self, slug):
        return self.rows("SELECT created_at, updated_at FROM quests WHERE slug = '{}'".format(slug))[0]

    def task_row(self, quest, tid):
        sql = "SELECT created_at, updated_at FROM quest_tasks WHERE quest = '{}' AND tid = '{}'"
        return self.rows(sql.format(quest, tid))[0]

    def test_updated_moves_and_created_stays(self):
        self.at(0, ["quest", "add", "q1", "--open", "--title", "q1", "--epic", "demo-epic", "--tasks", "T01,T03"], None)
        self.at(0, ["quest", "add", "q2", "--open", "--title", "q2", "--epic", "demo-epic", "--tasks", "T02"], None)
        created = _T0.isoformat()
        self.assertEqual(tuple(self.quest_row("q1")), (created, created))
        self.assertEqual(tuple(self.task_row("q1", "T01")), (created, created))

        self.start_party("alpha", "sess-1")
        self.at(5, ["quest", "take", "q1"], "sess-1")
        self.at(5, ["quest", "take", "q2"], "sess-1")
        self.assertEqual(self.quest_row("q1")["created_at"], created)
        self.assertEqual(self.quest_row("q1")["updated_at"], (_T0 + timedelta(minutes=5)).isoformat())

        self.at(10, ["task", "start", "q1/T01"], "sess-1")
        started = (_T0 + timedelta(minutes=10)).isoformat()
        self.assertEqual(tuple(self.task_row("q1", "T01")), (created, started))
        self.assertEqual(tuple(self.task_row("q1", "T03")), (created, created))

        self.at(15, ["task", "move", "q1/T03", "--to", "q2"], "sess-1")
        moved = (_T0 + timedelta(minutes=15)).isoformat()
        self.assertEqual(tuple(self.task_row("q2", "T03")), (created, moved))
        self.assertEqual(self.quest_row("q1")["updated_at"], moved)
        self.assertEqual(self.quest_row("q2")["updated_at"], moved)

        self.at(20, ["task", "add", "q2/T04", "--title", "extra"], "sess-1")
        added = (_T0 + timedelta(minutes=20)).isoformat()
        self.assertEqual(tuple(self.task_row("q2", "T04")), (added, added))
        self.assertEqual(tuple(self.quest_row("q2")), (created, added))

    def test_release_bumps_updated(self):
        self.at(0, ["quest", "add", "q1", "--open", "--title", "q1", "--epic", "demo-epic", "--tasks", "T02"], None)
        self.start_party("alpha", "sess-1")
        self.at(5, ["quest", "take", "q1"], "sess-1")
        self.at(9, ["quest", "release", "q1"], "sess-1")
        self.assertEqual(self.quest_row("q1")["updated_at"], (_T0 + timedelta(minutes=9)).isoformat())

    def test_values_survive_rebuild(self):
        self.at(0, ["quest", "add", "q1", "--open", "--title", "q1", "--epic", "demo-epic", "--tasks", "T02"], None)
        self.start_party("alpha", "sess-1")
        self.at(5, ["quest", "take", "q1"], "sess-1")
        self.at(10, ["task", "start", "q1/T02"], "sess-1")
        before = self.stamps()
        self.ok(["rebuild"], None)
        self.assertEqual(self.stamps(), before)

    def test_open_quest_shows_dates_in_cli_and_model(self):
        self.at(0, ["quest", "add", "q1", "--open", "--title", "Plan", "--epic", "demo-epic", "--tasks", "T02"], None)
        model = quest_board.data(self.ctx(), "acme")["open_quests"][0]
        self.assertTrue(model["dates"].startswith("created "))
        self.assertIn(
            "(epic demo-epic · {}): Plan".format(model["dates"]), "\n".join(quest_board.board(self.ctx(), "acme"))
        )
        summary = quest_board.summary_lines(dict(quest_board.data(self.ctx(), "acme"), name="acme"))
        self.assertIn("  open quest q1 (1 tasks · {})".format(model["dates"]), summary)

    def test_party_board_lines_and_models_show_dates(self):
        self.at(0, ["quest", "add", "q1", "--open", "--title", "Plan", "--epic", "demo-epic", "--tasks", "T02"], None)
        self.start_party("alpha", "sess-1")
        self.at(5, ["quest", "take", "q1"], "sess-1")
        self.at(10, ["task", "start", "q1/T02"], "sess-1")
        out = self.ok(["board"], "sess-1")
        self.assertIn("q1 — Plan", out)
        self.assertIn("created 2026", out)
        self.assertIn("· updated", out)


class UndatedRowsTests(QuestBoardTestCase):
    def undate(self):
        conn = sqlite3.connect(str(paths.db_path()))
        conn.execute("UPDATE quests SET created_at = NULL, updated_at = NULL")
        conn.execute("UPDATE quest_tasks SET created_at = NULL, updated_at = NULL")
        conn.commit()
        conn.close()

    def test_undated_rows_have_no_label_and_doctor_warns_until_rebuild(self):
        self.open_quest("q1", "T02", None)
        self.undate()
        model = quest_board.data(self.ctx(), "acme")["open_quests"][0]
        self.assertIsNone(model["dates"])
        lines = "\n".join(quest_board.board(self.ctx(), "acme"))
        self.assertIn("  q1 (epic demo-epic): q1", lines)
        self.assertNotIn("created", lines)
        _, out, _ = self.run_cli(["doctor"], None, self.repo_dir)
        self.assertIn(
            "2 rows predate stored dates: run guild compact, then guild rebuild, with no session working", out
        )
        self.ok(["rebuild"], None)
        _, out, _ = self.run_cli(["doctor"], None, self.repo_dir)
        self.assertNotIn("predate stored dates", out)

    def test_old_schema_db_gains_null_columns(self):
        db_path = self.data_home / "guild.db"
        raw = sqlite3.connect(str(db_path))
        raw.execute(
            "CREATE TABLE quests (slug TEXT PRIMARY KEY, project TEXT, party TEXT, epic TEXT, title TEXT NOT NULL, state TEXT NOT NULL)"
        )
        raw.execute(
            "CREATE TABLE quest_tasks (quest TEXT NOT NULL, tid TEXT NOT NULL, title TEXT NOT NULL, state TEXT NOT NULL, summary TEXT, blocked_reason TEXT, PRIMARY KEY (quest, tid))"
        )
        raw.execute("INSERT INTO quests VALUES ('q', 'acme', NULL, 'e', 't', 'active')")
        raw.execute("INSERT INTO quest_tasks VALUES ('q', 'T01', 't', 'queued', NULL, NULL)")
        raw.commit()
        raw.close()
        conn = db.connect(db_path)
        self.addCleanup(conn.close)
        row = conn.execute("SELECT * FROM quests").fetchone()
        self.assertEqual((row["created_at"], row["updated_at"]), (None, None))
        row = conn.execute("SELECT * FROM quest_tasks").fetchone()
        self.assertEqual((row["created_at"], row["updated_at"]), (None, None))
