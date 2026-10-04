import os
import signal
import subprocess
import tempfile

_ENCODING_ERRORS = "replace"


def _kill_group(process):
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return


def _result(exit_code, stdout, stderr, timed_out, error):
    return {
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": stderr,
        "timed_out": timed_out,
        "error": error,
    }


def _read_all(output_file):
    output_file.seek(0)
    return output_file.read().decode("utf-8", errors=_ENCODING_ERRORS)


def _launch(argv, stdout_file, stderr_file):
    return subprocess.Popen(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=stdout_file,
        stderr=stderr_file,
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


def run_capture(argv, timeout_seconds):
    with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
        try:
            process = _launch(argv, stdout_file, stderr_file)
        except OSError as error:
            return _result(None, "", "", False, str(error))
        timed_out = _wait(process, timeout_seconds)
        stdout = _read_all(stdout_file)
        stderr = _read_all(stderr_file)
    exit_code = None if timed_out else process.returncode
    return _result(exit_code, stdout, stderr, timed_out, None)
