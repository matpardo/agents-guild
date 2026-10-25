import os
import signal
import sys
import tempfile
import time
import unittest
from pathlib import Path

from guild import db, events, lifecycle
from guild.cli import _build_context
from tests.testutil import GuildTestCase

_TIMEOUT_SECONDS = 30


def _python(code):
    return [sys.executable, "-c", code]


def _run(argv, cwd, timeout_seconds):
    return lifecycle.run_process(argv, cwd, timeout_seconds)


class RunProcessTests(unittest.TestCase):
    def setUp(self):
        self._tempdir = tempfile.TemporaryDirectory()
        self.cwd = self._tempdir.name

    def tearDown(self):
        self._tempdir.cleanup()

    def test_captures_exit_zero_and_output(self):
        result = _run(_python("print('hello')"), self.cwd, _TIMEOUT_SECONDS)
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["output"], "hello\n")
        self.assertFalse(result["timed_out"])
        self.assertIsNone(result["error"])

    def test_captures_non_zero_exit(self):
        result = _run(_python("import sys; sys.exit(3)"), self.cwd, _TIMEOUT_SECONDS)
        self.assertEqual(result["exit_code"], 3)

    def test_merges_stderr_into_output(self):
        result = _run(
            _python("import sys; sys.stderr.write('oops'); sys.stdout.write('fine')"),
            self.cwd,
            _TIMEOUT_SECONDS,
        )
        self.assertIn("oops", result["output"])
        self.assertIn("fine", result["output"])

    def test_output_tail_is_capped_and_keeps_the_end(self):
        result = _run(_python("print('a' * 5000); print('the-end')"), self.cwd, _TIMEOUT_SECONDS)
        self.assertEqual(len(result["output"]), 2000)
        self.assertTrue(result["output"].endswith("the-end\n"))

    def test_output_has_control_sequences_stripped(self):
        result = _run(
            _python("import sys; sys.stdout.write('\\x1b[31mred\\x1b[0m\\x07bell')"),
            self.cwd,
            _TIMEOUT_SECONDS,
        )
        self.assertEqual(result["output"], "redbell")

    def test_undecodable_bytes_are_replaced(self):
        result = _run(_python("import sys; sys.stdout.buffer.write(b'ok\\xff')"), self.cwd, _TIMEOUT_SECONDS)
        self.assertTrue(result["output"].startswith("ok"))

    def test_timeout_kills_the_process_group(self):
        pid_file = Path(self.cwd) / "grandchild.pid"
        child_code = "import os, time; open({!r}, 'w').write(str(os.getpid())); time.sleep(60)".format(str(pid_file))
        code = "import subprocess, sys, time; subprocess.Popen([sys.executable, '-c', {!r}]); time.sleep(60)".format(
            child_code
        )
        started = time.monotonic()
        result = _run(_python(code), self.cwd, 2)
        self.assertLess(time.monotonic() - started, 30)
        self.assertTrue(result["timed_out"])
        self.assertIsNone(result["error"])
        grandchild = int(pid_file.read_text())
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and _alive(grandchild):
            time.sleep(0.05)
        self.assertFalse(_alive(grandchild))

    def _spawn_detached_grandchild_code(self, parent_tail):
        pid_file = Path(self.cwd) / "detached.pid"
        child_code = "import os, time; open({!r}, 'w').write(str(os.getpid())); time.sleep(15)".format(str(pid_file))
        code = (
            "import subprocess, sys, time\n"
            "subprocess.Popen([sys.executable, '-c', {!r}], start_new_session=True)\n"
            "time.sleep(1)\n{}"
        ).format(child_code, parent_tail)
        return code, pid_file

    def _reap_detached(self, pid_file):
        if not pid_file.exists():
            return
        try:
            os.kill(int(pid_file.read_text()), signal.SIGKILL)
        except ProcessLookupError:
            return

    def test_timeout_returns_when_a_detached_descendant_holds_stdout(self):
        code, pid_file = self._spawn_detached_grandchild_code("time.sleep(60)\n")
        self.addCleanup(self._reap_detached, pid_file)
        started = time.monotonic()
        result = _run(_python(code), self.cwd, 2)
        self.assertLess(time.monotonic() - started, 8)
        self.assertTrue(result["timed_out"])

    def test_success_returns_when_a_detached_descendant_outlives_the_command(self):
        code, pid_file = self._spawn_detached_grandchild_code("")
        self.addCleanup(self._reap_detached, pid_file)
        started = time.monotonic()
        result = _run(_python(code), self.cwd, _TIMEOUT_SECONDS)
        self.assertLess(time.monotonic() - started, 8)
        self.assertEqual(result["exit_code"], 0)

    def test_huge_output_returns_only_the_tail(self):
        result = _run(
            _python("import sys\nfor _ in range(50):\n    sys.stdout.write('x' * 1000000)\nprint('the-end')"),
            self.cwd,
            _TIMEOUT_SECONDS,
        )
        self.assertEqual(len(result["output"]), 2000)
        self.assertTrue(result["output"].endswith("the-end\n"))

    def test_stdin_is_closed(self):
        result = _run(_python("import sys; print(repr(sys.stdin.read()))"), self.cwd, _TIMEOUT_SECONDS)
        self.assertEqual(result["output"], "''\n")
        self.assertEqual(result["exit_code"], 0)

    def test_missing_executable_is_an_error(self):
        result = _run(["/nonexistent/guild-test-binary"], self.cwd, _TIMEOUT_SECONDS)
        self.assertIsNone(result["exit_code"])
        self.assertFalse(result["timed_out"])
        self.assertIn("No such file", result["error"])

    def test_missing_cwd_is_an_error(self):
        result = _run(_python("pass"), str(Path(self.cwd) / "gone"), _TIMEOUT_SECONDS)
        self.assertIsNone(result["exit_code"])
        self.assertIsNotNone(result["error"])

    def test_duration_is_recorded(self):
        result = _run(_python("pass"), self.cwd, _TIMEOUT_SECONDS)
        self.assertGreaterEqual(result["duration_ms"], 0)


def _alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


class LifecycleRanEventTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.ctx = _build_context("sess-1", self.root)

    def _record(self):
        payload = {
            "project": "acme",
            "event": "on_pr_merged",
            "repo": "acme/app",
            "triggers": ["acme/app#1"],
            "argv": ["scripts/cleanup-merged.sh"],
            "cwd": "/tmp/x",
            "status": "ok",
            "exit_code": 0,
            "duration_ms": 5,
            "output_tail": "done",
            "reason": None,
        }
        with db.writing(self.ctx.conn):
            events.record(
                self.ctx.conn, self.ctx.now, self.ctx.origin, None, None, "acme", "lifecycle.ran", "local", payload
            )

    def test_reducer_applies_event(self):
        self._record()
        count = self.ctx.conn.execute("SELECT COUNT(*) FROM events WHERE kind = 'lifecycle.ran'").fetchone()[0]
        self.assertEqual(count, 1)

    def test_rebuild_replays_event(self):
        self._record()
        code, out, err = self.run_cli(["rebuild"], None, None)
        self.assertEqual(code, 0, err)


if __name__ == "__main__":
    unittest.main()
