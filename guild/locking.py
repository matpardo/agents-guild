import contextlib
import fcntl

from guild import names, paths


@contextlib.contextmanager
def try_lock(lock_dir, file_name):
    private_dir = paths.ensure_private_dir(lock_dir)
    lock_path = names.ensure_within(private_dir / file_name, private_dir)
    with open(lock_path, "a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)
