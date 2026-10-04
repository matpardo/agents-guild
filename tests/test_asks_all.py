from datetime import datetime, timedelta, timezone

from guild import db, events, paths, timeutil
from guild.commands import board
from tests.testutil import GuildTestCase

_NOW = timeutil.utcnow()


class AsksAllTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha"], "sess-1", self.repo_dir)
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", self.repo_dir)
        self.run_cli(["task", "add", "demo/T01", "--title", "First"], "sess-1", self.repo_dir)
        self.conn = db.connect(paths.db_path())

    def _create(self, ask_id, party, question, moment):
        with db.writing(self.conn):
            events.record(
                self.conn, moment, "test@host", party, None, "acme", "ask.created", "local",
                {
                    "id": ask_id, "party": party, "question": question, "context": "x",
                    "refs": ["task:demo/T01"], "options": [],
                },
            )

    def _answer(self, ask_id, text, moment):
        with db.writing(self.conn):
            events.record(
                self.conn, moment, "test@host", None, None, "acme", "ask.answered", "local",
                {"id": ask_id, "answer": text},
            )

    def _dismiss(self, ask_id):
        with db.writing(self.conn):
            events.record(
                self.conn, _NOW, "test@host", None, None, "acme", "ask.dismissed", "local",
                {"id": ask_id},
            )

    def _seed_three(self):
        self.run_cli(["party", "start", "beta"], "sess-2", self.repo_dir)
        self._create(4, "beta", "Rename flag?", _NOW - timedelta(days=5))
        self._create(5, "alpha", "Which base branch?", _NOW - timedelta(days=2))
        self._create(7, "alpha", "Should the retry cap be 3 or 5?", _NOW)
        self._answer(5, "main", datetime(2026, 10, 3, 9, 12, 40, tzinfo=timezone.utc))
        self._dismiss(4)


class AnsweredAtReducerTests(AsksAllTests):
    def test_answered_at_is_the_event_timestamp(self):
        self._create(1, "alpha", "q?", _NOW)
        moment = datetime(2026, 10, 3, 9, 12, 40, tzinfo=timezone.utc)
        self._answer(1, "yes", moment)
        row = self.conn.execute("SELECT answered_at FROM asks WHERE id = 1").fetchone()
        self.assertEqual(row["answered_at"], timeutil.to_iso(moment))

    def test_answered_at_defaults_to_null_for_open_and_dismissed(self):
        self._create(1, "alpha", "q?", _NOW)
        self._create(2, "alpha", "r?", _NOW)
        self._dismiss(2)
        rows = self.conn.execute("SELECT answered_at FROM asks").fetchall()
        self.assertEqual([row["answered_at"] for row in rows], [None, None])

    def test_rebuild_keeps_answered_at(self):
        self._create(1, "alpha", "q?", _NOW)
        self._answer(1, "yes", _NOW)
        before = self.conn.execute("SELECT answered_at FROM asks").fetchone()["answered_at"]
        self.run_cli(["rebuild"], None, None)
        conn = db.connect(paths.db_path())
        self.assertEqual(conn.execute("SELECT answered_at FROM asks").fetchone()["answered_at"], before)


class AsksAllCliTests(AsksAllTests):
    def test_plain_asks_still_lists_only_open(self):
        self._seed_three()
        code, out, err = self.run_cli(["asks"], None, None)
        self.assertIn("Should the retry cap", out)
        self.assertNotIn("Which base branch?", out)
        self.assertNotIn("Rename flag?", out)

    def test_all_lists_every_state_with_answers_in_id_order(self):
        self._seed_three()
        code, out, err = self.run_cli(["asks", "--all"], None, None)
        self.assertEqual(code, 0, err)
        self.assertEqual(
            out.splitlines(),
            [
                "ASKS · 3 (1 open · 1 answered · 1 dismissed)",
                "  #4 beta · dismissed · Rename flag?",
                "  #5 alpha · answered · Which base branch?",
                "     answer: main",
                "     answered_at: 2026-10-03T09:12:40+00:00",
                "  #7 alpha · open · Should the retry cap be 3 or 5?",
                "",
            ],
        )

    def test_all_with_nothing(self):
        code, out, err = self.run_cli(["asks", "--all"], None, None)
        self.assertEqual(out.splitlines()[0], "ASKS · nothing")

    def test_party_narrows(self):
        self._seed_three()
        code, out, err = self.run_cli(["asks", "--all", "--party", "beta"], None, None)
        self.assertIn("Rename flag?", out)
        self.assertNotIn("Which base branch?", out)
        self.assertIn("ASKS · 1 (0 open · 0 answered · 1 dismissed)", out)

    def test_since_narrows_by_created_at(self):
        self._seed_three()
        code, out, err = self.run_cli(["asks", "--all", "--since", "3d"], None, None)
        self.assertNotIn("Rename flag?", out)
        self.assertIn("Which base branch?", out)

    def test_since_without_all_is_an_error(self):
        code, out, err = self.run_cli(["asks", "--since", "3d"], None, None)
        self.assertEqual(code, 1)
        self.assertIn("--party/--since need --all", err)

    def test_party_without_all_is_an_error(self):
        code, out, err = self.run_cli(["asks", "--party", "alpha"], None, None)
        self.assertEqual(code, 1)
        self.assertIn("--party/--since need --all", err)

    def test_unknown_party_is_an_error(self):
        code, out, err = self.run_cli(["asks", "--all", "--party", "nope"], None, None)
        self.assertEqual(code, 1)
        self.assertIn("unknown party 'nope'", err)

    def test_invalid_since_is_an_error(self):
        code, out, err = self.run_cli(["asks", "--all", "--since", "soon"], None, None)
        self.assertEqual(code, 1)
        self.assertIn("invalid duration", err)

    def test_render_all_strips_control_sequences_from_answers(self):
        self._create(1, "alpha", "q?", _NOW)
        self._answer(1, "ok\x1b[31mred", _NOW)
        code, out, err = self.run_cli(["asks", "--all"], None, None)
        self.assertNotIn("\x1b", out)


class AskModelTests(AsksAllTests):
    def test_model_exposes_state_answer_and_answered_at(self):
        self._create(1, "alpha", "q?", _NOW)
        self._answer(1, "ok\x1b[31m", _NOW)
        row = self.conn.execute("SELECT * FROM asks WHERE id = 1").fetchone()
        model = board._ask_model(self.conn, row)
        self.assertEqual(model["state"], "answered")
        self.assertEqual(model["answer"], "ok")
        self.assertEqual(model["answered_at"], timeutil.to_iso(_NOW))

    def test_open_ask_has_null_answer_and_answered_at(self):
        self._create(1, "alpha", "q?", _NOW)
        row = self.conn.execute("SELECT * FROM asks WHERE id = 1").fetchone()
        model = board._ask_model(self.conn, row)
        self.assertEqual((model["state"], model["answer"], model["answered_at"]), ("open", None, None))
