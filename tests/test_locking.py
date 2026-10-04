import fcntl
import unittest
from pathlib import Path
import tempfile

from guild import locking
from guild.errors import GuildError


class TryLockTests(unittest.TestCase):
    def setUp(self):
        self._tempdir = tempfile.TemporaryDirectory()
        self.lock_dir = Path(self._tempdir.name) / "locks"

    def tearDown(self):
        self._tempdir.cleanup()

    def test_free_lock_is_acquired_and_released(self):
        with locking.try_lock(self.lock_dir, "a.lock") as acquired:
            self.assertTrue(acquired)
        with locking.try_lock(self.lock_dir, "a.lock") as acquired_again:
            self.assertTrue(acquired_again)

    def test_held_lock_is_not_acquired(self):
        with locking.try_lock(self.lock_dir, "a.lock") as first:
            self.assertTrue(first)
            with locking.try_lock(self.lock_dir, "a.lock") as second:
                self.assertFalse(second)

    def test_different_names_do_not_block_each_other(self):
        with locking.try_lock(self.lock_dir, "a.lock") as first:
            with locking.try_lock(self.lock_dir, "b.lock") as second:
                self.assertTrue(first and second)

    def test_lock_is_released_after_an_exception(self):
        with self.assertRaises(RuntimeError):
            with locking.try_lock(self.lock_dir, "a.lock"):
                raise RuntimeError("boom")
        with open(self.lock_dir / "a.lock", "a") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def test_lock_directory_is_private(self):
        with locking.try_lock(self.lock_dir, "a.lock"):
            pass
        self.assertEqual(self.lock_dir.stat().st_mode & 0o777, 0o700)

    def test_file_name_escaping_the_directory_is_rejected(self):
        with self.assertRaises(GuildError):
            with locking.try_lock(self.lock_dir, "../escape.lock"):
                pass


if __name__ == "__main__":
    unittest.main()
