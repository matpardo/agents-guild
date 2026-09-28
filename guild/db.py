import contextlib
import sqlite3

from guild import paths, schema

_SIDECAR_SUFFIXES = ("-wal", "-shm")


def _secure_sidecar_files(path):
    for suffix in _SIDECAR_SUFFIXES:
        sidecar = path.parent / (path.name + suffix)
        if sidecar.exists():
            sidecar.chmod(0o600)


def connect(path):
    paths.ensure_private_dir(path.parent)
    conn = sqlite3.connect(str(path), isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.row_factory = sqlite3.Row
    schema.create_all(conn)
    path.chmod(0o600)
    _secure_sidecar_files(path)
    return conn


@contextlib.contextmanager
def writing(conn):
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except Exception:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")
