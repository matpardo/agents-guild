import sqlite3
import unittest

from guild import db, events, paths, timeutil
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

_OLD_NOTICES = """
CREATE TABLE notices (
    id INTEGER PRIMARY KEY,
    party TEXT,
    scope TEXT NOT NULL,
    text TEXT NOT NULL,
    until_condition TEXT,
    expires_at TEXT NOT NULL,
    state TEXT NOT NULL,
    created_at TEXT NOT NULL
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
    conn.execute(_OLD_NOTICES)
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
        for column in (
            "mergeable",
            "review_comment_count",
            "last_notified_comment_count",
            "last_activity_at",
            "checks_pending",
        ):
            self.assertIn(column, prs_columns)

        leader_row = conn.execute("SELECT * FROM leaders WHERE party = 'alpha'").fetchone()
        self.assertEqual(leader_row["session_name"], "old-session")
        self.assertIsNone(leader_row["handoff_path"])

        pr_row = conn.execute("SELECT * FROM prs WHERE repo = 'acme/app' AND number = 1").fetchone()
        self.assertEqual(pr_row["what"], "x")
        self.assertIsNone(pr_row["mergeable"])
        self.assertIsNone(pr_row["checks_pending"])

        for table in ("epics", "tasks"):
            self.assertEqual(conn.execute("SELECT COUNT(*) AS n FROM {}".format(table)).fetchone()["n"], 0)

    def test_old_schema_db_gains_human_flag_columns_initialised_to_zero(self):
        db_path = self.data_home / "guild.db"
        _make_old_schema_db(db_path)

        conn = db.connect(db_path)

        pr_row = conn.execute("SELECT * FROM prs WHERE number = 1").fetchone()
        self.assertEqual((pr_row["needs_ask_answer"], pr_row["needs_human_pr_review"]), (0, 0))

    def test_needs_human_lifecycle_rows_become_draft_with_the_ask_flag(self):
        db_path = self.data_home / "guild.db"
        _make_old_schema_db(db_path)
        raw = sqlite3.connect(str(db_path))
        raw.execute("UPDATE prs SET lifecycle = 'needs-human'")
        raw.commit()
        raw.close()

        conn = db.connect(db_path)
        pr_row = conn.execute("SELECT * FROM prs WHERE number = 1").fetchone()
        self.assertEqual((pr_row["lifecycle"], pr_row["needs_ask_answer"]), ("draft", 1))
        conn.close()

        again = db.connect(db_path)
        pr_row = again.execute("SELECT * FROM prs WHERE number = 1").fetchone()
        self.assertEqual((pr_row["lifecycle"], pr_row["needs_ask_answer"]), ("draft", 1))
        again.close()

    def test_old_schema_db_gains_asks_snapshot_and_answered_at_columns(self):
        db_path = self.data_home / "guild.db"
        raw = sqlite3.connect(str(db_path))
        raw.execute(
            "CREATE TABLE asks (id INTEGER PRIMARY KEY, party TEXT NOT NULL, question TEXT NOT NULL,"
            " context TEXT NOT NULL, refs TEXT NOT NULL, options TEXT NOT NULL, state TEXT NOT NULL,"
            " answer TEXT, created_at TEXT NOT NULL)"
        )
        raw.execute(
            "INSERT INTO asks VALUES (1, 'alpha', 'q', 'c', '[]', '[]', 'open', NULL, '2026-01-01T00:00:00+00:00')"
        )
        raw.commit()
        raw.close()

        conn = db.connect(db_path)
        conn.close()
        again = db.connect(db_path)

        row = again.execute("SELECT * FROM asks WHERE id = 1").fetchone()
        self.assertIsNone(row["snapshot"])
        self.assertIsNone(row["answered_at"])
        self.assertEqual(row["question"], "q")

    def test_old_schema_db_gains_the_mark_columns(self):
        db_path = self.data_home / "guild.db"
        _make_old_schema_db(db_path)

        conn = db.connect(db_path)

        pr_row = conn.execute("SELECT * FROM prs WHERE number = 1").fetchone()
        self.assertEqual((pr_row["fixes_main"], pr_row["fixes_flaky"]), (0, 0))
        conn.close()

        again = db.connect(db_path)
        pr_row = again.execute("SELECT * FROM prs WHERE number = 1").fetchone()
        self.assertEqual((pr_row["fixes_main"], pr_row["fixes_flaky"]), (0, 0))
        again.close()

    def test_old_schema_db_gains_prs_card_column(self):
        db_path = self.data_home / "guild.db"
        _make_old_schema_db(db_path)

        conn = db.connect(db_path)

        pr_row = conn.execute("SELECT * FROM prs WHERE number = 1").fetchone()
        self.assertIn("card", pr_row.keys())
        self.assertIsNone(pr_row["card"])

    def test_rebuild_replays_a_pr_tracked_event_without_card(self):
        conn = db.connect(paths.db_path())
        events.record(
            conn,
            timeutil.utcnow(),
            "tester@host",
            "alpha",
            None,
            "acme",
            "pr.tracked",
            "guild",
            {
                "repo": "acme/app",
                "number": 1,
                "party": "alpha",
                "task_quest": "demo",
                "task_tid": "T01",
                "what": "x",
                "waits": "y",
                "lifecycle": "draft",
                "branch": "feature/x",
                "title": "t",
                "gh_state": "OPEN",
                "gh_draft": True,
                "seeded": 0,
            },
        )
        conn.commit()
        conn.close()
        code, out, err = self.run_cli(["rebuild"], None, None)
        self.assertEqual(code, 0, err)
        conn = db.connect(paths.db_path())
        pr_row = conn.execute("SELECT * FROM prs WHERE number = 1").fetchone()
        conn.close()
        self.assertEqual((pr_row["task_tid"], pr_row["card"]), ("T01", None))

    def test_rebuild_replays_a_keeper_party_started_event_and_drops_the_column(self):
        conn = db.connect(paths.db_path())
        events.record(
            conn,
            timeutil.utcnow(),
            "tester@host",
            "alpha",
            "sess-1",
            "acme",
            "party.started",
            "local",
            {"party": "alpha", "session_name": "s", "keeper": True},
        )
        conn.commit()
        conn.close()
        code, out, err = self.run_cli(["rebuild"], None, None)
        self.assertEqual(code, 0, err)
        conn = db.connect(paths.db_path())
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(parties)").fetchall()}
        party = conn.execute("SELECT * FROM parties WHERE name = 'alpha'").fetchone()
        conn.close()
        self.assertNotIn("keeper", columns)
        self.assertEqual(party["state"], "active")

    def test_db_with_the_keeper_column_loses_it_and_keeps_its_rows(self):
        db_path = self.data_home / "guild.db"
        conn = db.connect(db_path)
        conn.execute("ALTER TABLE parties ADD COLUMN keeper INTEGER")
        conn.execute(
            "INSERT INTO parties (name, project, leader_session_id, generation, state, keeper)"
            " VALUES ('alpha', 'acme', 'sess-1', 1, 'active', 1)"
        )
        conn.commit()
        conn.close()

        again = db.connect(db_path)
        columns = {row["name"] for row in again.execute("PRAGMA table_info(parties)").fetchall()}
        party = again.execute("SELECT * FROM parties WHERE name = 'alpha'").fetchone()
        again.close()
        self.assertNotIn("keeper", columns)
        self.assertEqual(party["leader_session_id"], "sess-1")

    def test_rebuild_replays_an_old_fix_requested_event_as_a_no_op(self):
        conn = db.connect(paths.db_path())
        events.record(
            conn,
            timeutil.utcnow(),
            "tester@host",
            None,
            "sess-1",
            "acme",
            "pr.fix_requested",
            "guild",
            {"repo": "acme/app", "number": 1, "party": "alpha", "reasons": ["checks failing (1)"]},
        )
        conn.commit()
        conn.close()
        code, out, err = self.run_cli(["rebuild"], None, None)
        self.assertEqual(code, 0, err)

    def test_db_with_the_fix_requested_at_column_loses_it_and_keeps_its_rows(self):
        db_path = self.data_home / "guild.db"
        conn = db.connect(db_path)
        conn.execute("ALTER TABLE prs ADD COLUMN fix_requested_at TEXT")
        conn.execute(
            "INSERT INTO prs (repo, number, party, what, lifecycle, seeded, fix_requested_at)"
            " VALUES ('acme/app', 1, 'alpha', 'w', 'draft', 0, '2026-10-11T10:00:00+00:00')"
        )
        conn.commit()
        conn.close()

        again = db.connect(db_path)
        columns = {row["name"] for row in again.execute("PRAGMA table_info(prs)").fetchall()}
        pr_row = again.execute("SELECT * FROM prs WHERE number = 1").fetchone()
        again.close()
        self.assertNotIn("fix_requested_at", columns)
        self.assertEqual(pr_row["repo"], "acme/app")

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

    def test_old_schema_db_gains_notices_announces_column(self):
        db_path = self.data_home / "guild.db"
        _make_old_schema_db(db_path)

        conn = db.connect(db_path)

        notices_columns = {row["name"] for row in conn.execute("PRAGMA table_info(notices)").fetchall()}
        self.assertIn("announces", notices_columns)

    def test_old_schema_db_gains_notices_seen_at_column(self):
        db_path = self.data_home / "guild.db"
        _make_old_schema_db(db_path)

        conn = db.connect(db_path)

        notices_columns = {row["name"] for row in conn.execute("PRAGMA table_info(notices)").fetchall()}
        self.assertIn("seen_at", notices_columns)

    def test_migrated_db_can_mark_a_notice_seen(self):
        paths.ensure_private_dir(paths.db_path().parent)
        _make_old_schema_db(paths.db_path())
        self.run_cli(["notice", "create", "pipeline down", "--to", "guild", "--ttl", "5h"], None, None)
        code, out, err = self.run_cli(["notice", "seen", "1"], None, None)
        self.assertEqual(code, 0, err)

    def test_old_schema_db_gains_raid_members_table(self):
        db_path = self.data_home / "guild.db"
        _make_old_schema_db(db_path)

        conn = db.connect(db_path)

        raid_members_columns = {row["name"] for row in conn.execute("PRAGMA table_info(raid_members)").fetchall()}
        self.assertEqual(raid_members_columns, {"raid", "party", "expires_at"})
        self.assertEqual(conn.execute("SELECT COUNT(*) AS n FROM raid_members").fetchone()["n"], 0)

    def test_raid_members_lead_column_is_dropped_and_rows_kept(self):
        db_path = self.data_home / "guild.db"
        legacy = sqlite3.connect(str(db_path))
        legacy.execute(
            "CREATE TABLE raid_members (raid TEXT NOT NULL, party TEXT NOT NULL,"
            " expires_at TEXT, lead INTEGER, PRIMARY KEY (raid, party))"
        )
        legacy.execute("INSERT INTO raid_members VALUES ('ci', 'alpha', NULL, 1)")
        legacy.commit()
        legacy.close()

        conn = db.connect(db_path)

        raid_members_columns = {row["name"] for row in conn.execute("PRAGMA table_info(raid_members)").fetchall()}
        self.assertEqual(raid_members_columns, {"raid", "party", "expires_at"})
        row = conn.execute("SELECT * FROM raid_members WHERE raid = 'ci' AND party = 'alpha'").fetchone()
        self.assertIsNotNone(row)

    def test_not_null_raid_expiry_is_relaxed_and_rows_kept(self):
        db_path = self.data_home / "guild.db"
        legacy = sqlite3.connect(str(db_path))
        legacy.execute(
            "CREATE TABLE raid_members (raid TEXT NOT NULL, party TEXT NOT NULL,"
            " expires_at TEXT NOT NULL, PRIMARY KEY (raid, party))"
        )
        legacy.execute("INSERT INTO raid_members VALUES ('ci', 'alpha', '2099-01-01T00:00:00+00:00')")
        legacy.commit()
        legacy.close()

        conn = db.connect(db_path)

        expiry = next(
            row for row in conn.execute("PRAGMA table_info(raid_members)").fetchall() if row["name"] == "expires_at"
        )
        self.assertEqual(expiry["notnull"], 0)
        rows = conn.execute("SELECT raid, party, expires_at FROM raid_members").fetchall()
        self.assertEqual([tuple(row) for row in rows], [("ci", "alpha", "2099-01-01T00:00:00+00:00")])
        conn.execute("INSERT INTO raid_members (raid, party, expires_at) VALUES ('ci', 'beta', NULL)")

    def test_old_prs_table_gains_diff_columns_and_shared_areas_table(self):
        db_path = self.data_home / "guild.db"
        _make_old_schema_db(db_path)

        conn = db.connect(db_path)

        prs_columns = {row["name"] for row in conn.execute("PRAGMA table_info(prs)").fetchall()}
        self.assertTrue({"additions", "deletions", "created_at"} <= prs_columns)
        row = conn.execute("SELECT additions, deletions, created_at FROM prs WHERE number = 1").fetchone()
        self.assertEqual(tuple(row), (None, None, None))
        self.assertTrue({"review_decision", "merge_state", "base_branch", "unresolved_threads"} <= prs_columns)
        self.assertEqual(conn.execute("SELECT COUNT(*) AS n FROM pr_shared_areas").fetchone()["n"], 0)

    def test_rebuild_works_after_migration(self):
        db_path = self.data_home / "guild.db"
        _make_old_schema_db(db_path)
        code, out, err = self.run_cli(["rebuild"], None, self.root)
        self.assertEqual(code, 0)
        self.assertIn("rebuilt from", out)


if __name__ == "__main__":
    unittest.main()
