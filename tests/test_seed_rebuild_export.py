import json

from guild import db, paths, schema
from tests.testutil import GuildTestCase

_SEED = {
    "parties": [{"name": "alpha", "project": "acme", "session_name": "demo-session"}],
    "quests": [
        {
            "slug": "wave1",
            "project": "acme",
            "party": "alpha",
            "epic": "compliance",
            "title": "Wave 1",
            "tasks": [
                {"tid": "T09", "title": "Flags per school", "state": "active", "summary": "in review"},
                {"tid": "T04", "title": "Guardian scoping", "state": "queued"},
                {"tid": "T05", "title": "Blocked one", "state": "blocked", "reason": "waiting on ci"},
                {"tid": "T06", "title": "Shipped one", "state": "done", "summary": "merged"},
            ],
        }
    ],
    "prs": [
        {
            "repo": "acme/app",
            "number": 894,
            "party": "alpha",
            "task_quest": "wave1",
            "task_tid": "T09",
            "what": "per-school flags",
            "waits": "one more review",
            "lifecycle": "needs-human",
        }
    ],
    "asks": [
        {
            "party": "alpha",
            "question": "one more round?",
            "context": "numbering resets per tenant",
            "refs": ["pr:acme/app#894"],
            "options": ["extra round", "ship as is"],
        }
    ],
    "notices": [{"party": "alpha", "text": "ci quota fixed", "scope": "guild", "ttl": "8h"}],
}


class SeedTests(GuildTestCase):
    def test_seed_loads_state(self):
        seed_file = self.root / "seed.json"
        seed_file.write_text(json.dumps(_SEED))
        code, out, err = self.run_cli(["seed", str(seed_file)], None, None)
        self.assertEqual(code, 0)
        code, out, err = self.run_cli(["board"], None, None)
        self.assertIn("━━ alpha", out)
        self.assertIn("▶ T09  Flags per school", out)
        self.assertIn("in review", out)
        self.assertIn("queued: T04", out)
        self.assertIn("blocked: T05 — waiting on ci", out)
        self.assertNotIn("T06", out)
        self.assertIn("app#894  needs-human", out)
        code, out, err = self.run_cli(["asks"], None, None)
        self.assertIn("one more round?", out)

    def test_seed_missing_file(self):
        code, out, err = self.run_cli(["seed", "/tmp/_no_such_seed.json"], None, None)
        self.assertEqual(code, 1)


def _dump_projections(conn):
    dump = {}
    for table in schema.PROJECTION_TABLES:
        rows = conn.execute("SELECT * FROM {} ORDER BY rowid".format(table)).fetchall()
        dump[table] = [dict(row) for row in rows]
    return dump


class RebuildTests(GuildTestCase):
    def test_rebuild_reproduces_identical_projections(self):
        seed_file = self.root / "seed.json"
        seed_file.write_text(json.dumps(_SEED))
        self.run_cli(["seed", str(seed_file)], None, None)

        conn = db.connect(paths.db_path())
        before = _dump_projections(conn)

        code, out, err = self.run_cli(["rebuild"], None, None)
        self.assertEqual(code, 0)

        conn = db.connect(paths.db_path())
        after = _dump_projections(conn)
        self.assertEqual(before, after)


class ArchivedNoticeRebuildTests(GuildTestCase):
    def test_rebuild_keeps_archived_state(self):
        self.run_cli(["notice", "create", "kept", "--to", "guild", "--ttl", "5h"], None, None)
        self.run_cli(["notice", "create", "restored", "--to", "guild", "--ttl", "5h"], None, None)
        self.run_cli(["notice", "archive", "1"], None, None)
        self.run_cli(["notice", "archive", "2"], None, None)
        self.run_cli(["notice", "unarchive", "2"], None, None)
        before = _dump_projections(db.connect(paths.db_path()))

        code, out, err = self.run_cli(["rebuild"], None, None)
        self.assertEqual(code, 0, err)

        self.assertEqual(before, _dump_projections(db.connect(paths.db_path())))
        code, out, err = self.run_cli(["notices", "--archived"], None, None)
        self.assertIn("kept", out)
        self.assertNotIn("restored", out)


class ExportTests(GuildTestCase):
    def test_export_only_includes_guild_visibility(self):
        seed_file = self.root / "seed.json"
        seed_file.write_text(json.dumps(_SEED))
        self.run_cli(["seed", str(seed_file)], None, None)
        code, out, err = self.run_cli(["export", "--visibility", "guild"], None, None)
        self.assertEqual(code, 0)
        lines = [line for line in out.splitlines() if line]
        kinds = [json.loads(line)["kind"] for line in lines]
        self.assertIn("pr.tracked", kinds)
        self.assertIn("notice.created", kinds)
        self.assertNotIn("ask.created", kinds)
        self.assertNotIn("quest.added", kinds)


if __name__ == "__main__":
    import unittest

    unittest.main()
