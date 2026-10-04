import tempfile
import unittest
from pathlib import Path

from guild.resources import machine

_MEMINFO = """MemTotal:       32768000 kB
MemFree:         1000000 kB
MemAvailable:   16384000 kB
Buffers:          100000 kB
"""


class MachineTests(unittest.TestCase):
    def setUp(self):
        self._tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tempdir.name)
        self.meminfo = self.root / "meminfo"
        self.db = self.root / "guild.db"

    def tearDown(self):
        self._tempdir.cleanup()

    def test_meminfo_is_converted_from_kilobytes(self):
        self.meminfo.write_text(_MEMINFO)
        self.assertEqual(machine.read_memory(self.meminfo), (32768000 * 1024, 16384000 * 1024))

    def test_missing_meminfo_is_null_not_zero(self):
        self.assertEqual(machine.read_memory(self.root / "nope"), (None, None))

    def test_meminfo_without_available_is_null(self):
        self.meminfo.write_text("MemTotal:       100 kB\n")
        self.assertEqual(machine.read_memory(self.meminfo), (None, None))

    def test_garbage_meminfo_is_null(self):
        self.meminfo.write_text("MemTotal: lots kB\nMemAvailable: some kB\n")
        self.assertEqual(machine.read_memory(self.meminfo), (None, None))

    def test_database_bytes_include_wal_and_shm(self):
        self.db.write_bytes(b"x" * 100)
        (self.root / "guild.db-wal").write_bytes(b"x" * 20)
        (self.root / "guild.db-shm").write_bytes(b"x" * 3)
        self.assertEqual(machine.database_bytes(self.db), 123)

    def test_database_bytes_tolerate_missing_sidecars(self):
        self.db.write_bytes(b"x" * 100)
        self.assertEqual(machine.database_bytes(self.db), 100)

    def test_snapshot_reports_disk_memory_and_database(self):
        self.meminfo.write_text(_MEMINFO)
        self.db.write_bytes(b"x" * 100)
        snapshot = machine.snapshot(self.root, self.meminfo, self.db)
        self.assertGreater(snapshot["disk_total"], 0)
        self.assertGreaterEqual(snapshot["disk_total"], snapshot["disk_used"])
        self.assertEqual(snapshot["mem_total"], 32768000 * 1024)
        self.assertEqual(snapshot["mem_available"], 16384000 * 1024)
        self.assertEqual(snapshot["guild_db_bytes"], 100)

    def test_snapshot_disk_is_null_when_path_is_unreadable(self):
        snapshot = machine.snapshot(self.root / "gone", self.meminfo, self.db)
        self.assertIsNone(snapshot["disk_total"])
        self.assertIsNone(snapshot["disk_used"])


if __name__ == "__main__":
    unittest.main()
