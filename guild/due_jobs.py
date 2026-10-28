import os
import subprocess
import sys
from pathlib import Path

from guild import paths

_REPO_ROOT = Path(__file__).resolve().parents[1]
_ISOLATED_LAUNCHER = (
    "import runpy, sys; sys.path.insert(0, sys.argv.pop(1)); sys.argv[0] = 'guild'; "
    "runpy.run_module('guild', run_name='__main__', alter_sys=True)"
)
_MINUTE = 60
_HOUR = 60 * _MINUTE
_DAY = 24 * _HOUR
_LOW_PRIORITY_NICE = 19

JOBS = {
    "sync-gh": (("sync", "--source", "gh"), 10 * _MINUTE, False),
    "sync-sdd": (("sync", "--source", "sdd", "--all-projects"), 10 * _MINUTE, False),
    "sync-tracker": (("sync", "--source", "tracker", "--all-projects"), 10 * _MINUTE, False),
    "sync-bases": (("sync", "--source", "bases"), _MINUTE, False),
    "resources-collect": (("resources", "collect"), 2 * _HOUR, True),
    "compact": (("compact",), _DAY, True),
}


def _lower_priority():
    os.nice(_LOW_PRIORITY_NICE)


def spawn_detached(argv, cwd, low_priority):
    try:
        subprocess.Popen(
            [sys.executable, "-I", "-c", _ISOLATED_LAUNCHER, str(_REPO_ROOT)] + list(argv),
            cwd=str(cwd),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            preexec_fn=_lower_priority if low_priority else None,
        )
    except OSError:
        return


def _is_due(stamp, interval, now_epoch):
    return not stamp.exists() or now_epoch - stamp.stat().st_mtime >= interval


def spawn_due(state_dir, cwd, now_epoch, spawner):
    stamp_dir = paths.ensure_private_dir(state_dir / "due")
    for name, (argv, interval, low_priority) in JOBS.items():
        stamp = stamp_dir / name
        if not _is_due(stamp, interval, now_epoch):
            continue
        stamp.touch()
        os.utime(stamp, (now_epoch, now_epoch))
        spawner(argv, cwd, low_priority)
