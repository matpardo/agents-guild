import os
import signal
import subprocess
import tempfile
import time

from guild import sanitize

_OUTPUT_TAIL_CHARS = 2000
_OUTPUT_TAIL_BYTES = 8000


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


def _read_tail(output_file):
    size = output_file.seek(0, os.SEEK_END)
    output_file.seek(max(0, size - _OUTPUT_TAIL_BYTES))
    return output_tail(output_file.read(_OUTPUT_TAIL_BYTES))


def _launch(argv, cwd, output_file):
    return subprocess.Popen(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=output_file,
        stderr=subprocess.STDOUT,
        cwd=cwd,
        start_new_session=True,
    )


def _wait(process, timeout_seconds):
    try:
        process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        _kill_group(process)
        process.wait()
        return True
    return False


def run_process(argv, cwd, timeout_seconds):
    started = time.monotonic()
    with tempfile.TemporaryFile() as output_file:
        try:
            process = _launch(argv, cwd, output_file)
        except OSError as error:
            return _result(None, "", False, str(error), started)
        timed_out = _wait(process, timeout_seconds)
        output = _read_tail(output_file)
    exit_code = None if timed_out else process.returncode
    return _result(exit_code, output, timed_out, None, started)
