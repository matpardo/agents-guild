import sqlite3

POLL_SECONDS = 15


def timeout_label(timeout):
    return "{}m".format(int(timeout.total_seconds() // 60))


def until(read, check, timeout, sleep, clock):
    deadline = clock() + timeout
    snapshot = read()
    while True:
        result = check(snapshot)
        if result is not None:
            return result
        remaining = (deadline - clock()).total_seconds()
        if remaining <= 0:
            return None
        sleep(min(POLL_SECONDS, remaining))
        snapshot = _reread(read, snapshot)


def _reread(read, previous):
    try:
        return read()
    except sqlite3.OperationalError:
        return previous
