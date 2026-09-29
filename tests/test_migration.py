import sqlite3
import unittest

from guild import db, schema
from tests.testutil import GuildTestCase

_OLD_LEADERS = """
CREATE TABLE leaders (
    party TEXT NOT NULL,
    generation INTEGER NOT NULL,
    session_id TEXT,
    session_name TEXT,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    PRIMARY KEY (party, generation)
)
"""

_OLD_PRS = """
CREATE TABLE prs (
    repo TEXT NOT NULL,
    number INTEGER NOT NULL,
    party TEXT NOT NULL,
    task_quest TEXT,
    task_tid TEXT,
    what TEXT NOT NULL,
    waits TEXT,
    lifecycle TEXT NOT NULL,
    branch TEXT,
    title TEXT,
    gh_state TEXT,
    gh_draft INTEGER,
    checks_failing INTEGER,
    checks_passing INTEGER,
    seeded INTEGER NOT NULL,
    synced_at TEXT,
    PRIMARY KEY (repo, number)
)
"""


def _make_old_schema_db(path):
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute(_OLD_LEADERS)
    conn.execute(_OLD_PRS)
    conn.execute(
        "INSERT INTO leaders (party, generation, session_id, session_name, started_at, ended_at)"
        " VALUES ('alpha', 1, 'sess-1', 'old-session', '2026-01-01T00:00:00+00:00', NULL)"
    )
    conn.execute(
        "INSERT INTO prs (repo, number, party, task_quest, task_tid, what, waits, lifecycle,"
        " branch, title, gh_state, gh_draft, checks_failing, checks_passing, seeded, synced_at)"
        " VALUES ('acme/app', 1, 'alpha', 'demo', 'T01', 'x', 'y', 'draft',"
        " 'feature/x', 't', 'OPEN', 1, NULL, NULL, 0, NULL)"
    )
    conn.commit()
    conn.close()


class MigrationTests(GuildTestCase):
    def test_old_schema_db_survives_migration(self):
        db_path = self.data_home / "guild.db"
        _make_old_schema_db(db_path)

        conn = db.connect(db_path)

        leaders_columns = conn.execute("PRAGMA table_info(leaders)").fetchall()
        self.assertIn("handoff_path", {row["name"] for row in leaders_columns})

        prs_columns = {row["name"] for row in conn.execute("PRAGMA table_info(prs)").fetchall()}
        for column in ("mergeable", "review_comment_count", "last_notified_comment_count", "last_activity_at"):
            self.assertIn(column, prs_columns)

        leader_row = conn.execute("SELECT * FROM leaders WHERE party = 'alpha'").fetchone()
        self.assertEqual(leader_row["session_name"], "old-session")
        self.assertIsNone(leader_row["handoff_path"])

        pr_row = conn.execute("SELECT * FROM prs WHERE repo = 'acme/app' AND number = 1").fetchone()
        self.assertEqual(pr_row["what"], "x")
        self.assertIsNone(pr_row["mergeable"])

        for table in ("epics", "tasks"):
            self.assertEqual(conn.execute("SELECT COUNT(*) AS n FROM {}".format(table)).fetchone()["n"], 0)

    def test_old_schema_db_gains_cards_table(self):
        db_path = self.data_home / "guild.db"
        _make_old_schema_db(db_path)

        conn = db.connect(db_path)

        cards_columns = {row["name"] for row in conn.execute("PRAGMA table_info(cards)").fetchall()}
        self.assertEqual(
            cards_columns,
            {"project", "key", "status", "status_category", "issue_type", "parent_key"},
        )
        self.assertEqual(conn.execute("SELECT COUNT(*) AS n FROM cards").fetchone()["n"], 0)

    def test_old_schema_db_gains_raid_members_table(self):
        db_path = self.data_home / "guild.db"
        _make_old_schema_db(db_path)

        conn = db.connect(db_path)

        raid_members_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(raid_members)").fetchall()
        }
        self.assertEqual(raid_members_columns, {"raid", "party", "expires_at"})
        self.assertEqual(conn.execute("SELECT COUNT(*) AS n FROM raid_members").fetchone()["n"], 0)

    def test_rebuild_works_after_migration(self):
        db_path = self.data_home / "guild.db"
        _make_old_schema_db(db_path)
        code, out, err = self.run_cli(["rebuild"], None, self.root)
        self.assertEqual(code, 0)
        self.assertIn("rebuilt from", out)


if __name__ == "__main__":
    unittest.main()
