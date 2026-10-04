import os
import signal
import sys
import time
import unittest
from pathlib import Path
import tempfile

from guild import probe

_TIMEOUT_SECONDS = 30


def _python(code):
    return [sys.executable, "-c", code]


def _alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


class RunCaptureTests(unittest.TestCase):
    def test_captures_stdout_and_exit_zero(self):
        result = probe.run_capture(_python("print('hello')"), _TIMEOUT_SECONDS)
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["stdout"], "hello\n")
        self.assertEqual(result["stderr"], "")
        self.assertFalse(result["timed_out"])
        self.assertIsNone(result["error"])

    def test_captures_stderr_apart_from_stdout(self):
        result = probe.run_capture(
            _python("import sys; sys.stderr.write('oops'); sys.stdout.write('fine')"), _TIMEOUT_SECONDS
        )
        self.assertEqual(result["stdout"], "fine")
        self.assertEqual(result["stderr"], "oops")

    def test_captures_non_zero_exit(self):
        result = probe.run_capture(_python("import sys; sys.exit(3)"), _TIMEOUT_SECONDS)
        self.assertEqual(result["exit_code"], 3)

    def test_missing_binary_is_an_error_not_an_exception(self):
        result = probe.run_capture(["/nonexistent/guild-test-binary"], _TIMEOUT_SECONDS)
        self.assertIsNone(result["exit_code"])
        self.assertFalse(result["timed_out"])
        self.assertIn("No such file", result["error"])
        self.assertEqual(result["stdout"], "")
        self.assertEqual(result["stderr"], "")

    def test_undecodable_bytes_are_replaced(self):
        result = probe.run_capture(_python("import sys; sys.stdout.buffer.write(b'ok\\xff')"), _TIMEOUT_SECONDS)
        self.assertTrue(result["stdout"].startswith("ok"))

    def test_stdin_is_closed(self):
        result = probe.run_capture(_python("import sys; print(repr(sys.stdin.read()))"), _TIMEOUT_SECONDS)
        self.assertEqual(result["stdout"], "''\n")

    def test_timeout_kills_the_process_group(self):
        with tempfile.TemporaryDirectory() as directory:
            pid_file = Path(directory) / "grandchild.pid"
            child_code = "import os, time; open({!r}, 'w').write(str(os.getpid())); time.sleep(60)".format(
                str(pid_file)
            )
            code = (
                "import subprocess, sys, time; "
                "subprocess.Popen([sys.executable, '-c', {!r}]); time.sleep(60)"
            ).format(child_code)
            started = time.monotonic()
            result = probe.run_capture(_python(code), 2)
            self.assertLess(time.monotonic() - started, 30)
            self.assertTrue(result["timed_out"])
            self.assertIsNone(result["exit_code"])
            self.assertIsNone(result["error"])
            grandchild = int(pid_file.read_text())
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and _alive(grandchild):
                time.sleep(0.05)
            if _alive(grandchild):
                os.kill(grandchild, signal.SIGKILL)
            self.assertFalse(_alive(grandchild))

    def test_large_output_is_returned_whole(self):
        result = probe.run_capture(
            _python("import sys; sys.stdout.write('x' * 3000000)"), _TIMEOUT_SECONDS
        )
        self.assertEqual(len(result["stdout"]), 3000000)


if __name__ == "__main__":
    unittest.main()
