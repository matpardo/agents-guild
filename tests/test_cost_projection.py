from guild import db, events, schema
from guild.cli import _build_context
from guild.commands import rebuild as rebuild_commands
from tests.testutil import GuildTestCase


def _payload(day, model, quest, tid, input_tokens, cache_creation, cache_read, output_tokens):
    return {
        "day": day,
        "model": model,
        "quest": quest,
        "tid": tid,
        "account": "",
        "input_tokens": input_tokens,
        "cache_creation_tokens": cache_creation,
        "cache_read_tokens": cache_read,
        "output_tokens": output_tokens,
    }


class CostProjectionTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.ctx = _build_context("sess-1", self.root)

    def _sample(self, party, session_id, payload):
        with db.writing(self.ctx.conn):
            events.record(
                self.ctx.conn, self.ctx.now, self.ctx.origin, party, session_id, None, "cost.sampled", "local", payload
            )

    def _rows(self):
        return self.ctx.conn.execute(
            "SELECT * FROM cost_samples ORDER BY session_id, day, model, party, quest, tid"
        ).fetchall()

    def test_event_inserts_row(self):
        self._sample("alpha", "sess-1", _payload("2026-10-01", "m", "q", "T01", 1, 2, 3, 4))
        rows = self._rows()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual((row["session_id"], row["day"], row["model"]), ("sess-1", "2026-10-01", "m"))
        self.assertEqual((row["party"], row["quest"], row["tid"]), ("alpha", "q", "T01"))
        self.assertEqual(
            (row["input_tokens"], row["cache_creation_tokens"], row["cache_read_tokens"], row["output_tokens"]),
            (1, 2, 3, 4),
        )

    def test_same_key_sums(self):
        self._sample("alpha", "sess-1", _payload("2026-10-01", "m", "q", "T01", 1, 2, 3, 4))
        self._sample("alpha", "sess-1", _payload("2026-10-01", "m", "q", "T01", 10, 20, 30, 40))
        rows = self._rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            (rows[0]["input_tokens"], rows[0]["cache_creation_tokens"], rows[0]["cache_read_tokens"], rows[0]["output_tokens"]),
            (11, 22, 33, 44),
        )

    def test_different_keys_stay_separate(self):
        self._sample("alpha", "sess-1", _payload("2026-10-01", "m", "q", "T01", 1, 0, 0, 0))
        self._sample("alpha", "sess-1", _payload("2026-10-01", "m", "q", "T02", 1, 0, 0, 0))
        self._sample("alpha", "sess-1", _payload("2026-10-01", "m", "r", "T01", 1, 0, 0, 0))
        self._sample("beta", "sess-1", _payload("2026-10-01", "m", "q", "T01", 1, 0, 0, 0))
        self._sample(None, "sess-1", _payload("2026-10-01", "m", "", "", 1, 0, 0, 0))
        self.assertEqual(len(self._rows()), 5)
        unbound = self.ctx.conn.execute("SELECT party FROM cost_samples WHERE quest = ''").fetchone()
        self.assertEqual(unbound["party"], "")

    def test_rebuild_reproduces_samples_and_keeps_cursors(self):
        self._sample("alpha", "sess-1", _payload("2026-10-01", "m", "q", "T01", 1, 2, 3, 4))
        self._sample("alpha", "sess-1", _payload("2026-10-01", "m", "q", "T01", 1, 2, 3, 4))
        self.ctx.conn.execute("INSERT INTO transcript_cursors (path, offset) VALUES ('/x.jsonl', 42)")
        before = [dict(row) for row in self._rows()]
        rebuild_commands.run(self.ctx)
        self.assertEqual([dict(row) for row in self._rows()], before)
        cursor = self.ctx.conn.execute("SELECT offset FROM transcript_cursors WHERE path = '/x.jsonl'").fetchone()
        self.assertEqual(cursor["offset"], 42)

    def test_create_all_is_idempotent(self):
        self._sample("alpha", "sess-1", _payload("2026-10-01", "m", "q", "T01", 1, 2, 3, 4))
        schema.create_all(self.ctx.conn)
        schema.create_all(self.ctx.conn)
        self.assertEqual(len(self._rows()), 1)
