import sqlite3
import tempfile
import unittest
from pathlib import Path

from guild import db


class ConnectUnderWriteLockTests(unittest.TestCase):
    def setUp(self):
        self._tempdir = tempfile.TemporaryDirectory()
        self.path = Path(self._tempdir.name) / "guild.db"
        db.connect(self.path).close()
        self.writer = sqlite3.connect(str(self.path), isolation_level=None)
        self.writer.execute("BEGIN IMMEDIATE")

    def tearDown(self):
        self.writer.execute("ROLLBACK")
        self.writer.close()
        self._tempdir.cleanup()

    def test_connect_on_a_current_schema_takes_no_write_lock(self):
        conn = db.connect(self.path)
        self.addCleanup(conn.close)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM prs").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
