import os
import signal
import subprocess
import time

from guild import sanitize

_OUTPUT_TAIL_CHARS = 2000


def output_tail(raw):
    text = sanitize.strip_control_sequences(raw.decode("utf-8", errors="replace"))
    return text[-_OUTPUT_TAIL_CHARS:]


def _kill_group(process):
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return


def _result(exit_code, output, timed_out, error, started):
    return {
        "exit_code": exit_code,
        "output": output,
        "timed_out": timed_out,
        "error": error,
        "duration_ms": int((time.monotonic() - started) * 1000),
    }


def run_process(argv, cwd, timeout_seconds):
    started = time.monotonic()
    try:
        process = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=cwd,
            start_new_session=True,
        )
    except OSError as error:
        return _result(None, "", False, str(error), started)
    try:
        raw, _ = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        _kill_group(process)
        raw, _ = process.communicate()
        return _result(None, output_tail(raw), True, None, started)
    return _result(process.returncode, output_tail(raw), False, None, started)
