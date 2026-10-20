import json
import sys
import time
import unittest
from pathlib import Path

from guild import lifecycle, trace_validator

_SHA = "a" * 40
_DISCUSSION = {"comments": [{"body": "c"}], "reviews": [{"body": "r"}]}


def _project(command, timeout_seconds, pii_patterns=None):
    project = {"name": "acme", "human_ready": {"trace_validator": {"command": command, "timeout_seconds": timeout_seconds}}}
    if pii_patterns is not None:
        project["pii_patterns"] = pii_patterns
    return project


def _result(exit_code, output, timed_out=False, error=None):
    return {"exit_code": exit_code, "output": output, "timed_out": timed_out, "error": error, "duration_ms": 1}


class FakeRunner:
    def __init__(self, result, action=None, error=None):
        self.result = result
        self.action = action
        self.error = error
        self.calls = []

    def __call__(self, argv, cwd, timeout_seconds):
        path = Path(argv[-1])
        self.calls.append(
            {
                "argv": argv,
                "cwd": cwd,
                "timeout": timeout_seconds,
                "mode": path.stat().st_mode & 0o777,
                "content": json.loads(path.read_text()),
                "path": path,
            }
        )
        if self.action:
            self.action(path)
        if self.error:
            raise self.error
        return self.result


def _check(runner, command=("v", "{comments_file}"), number=7, sha=_SHA, timeout=30, patterns=None):
    return trace_validator.check(_project(list(command), timeout, patterns), "/repo", number, sha, _DISCUSSION, runner)


class ArgvTests(unittest.TestCase):
    def test_placeholders_replaced_inside_elements_as_a_list(self):
        runner = FakeRunner(_result(0, ""))
        _check(runner, command=("v", "--sha={head_sha}", "pr{pr}x", "{other}", "{comments_file}"))
        call = runner.calls[0]
        self.assertEqual(call["argv"][:4], ["v", "--sha=" + _SHA, "pr7x", "{other}"])
        self.assertEqual(call["argv"][4], str(call["path"]))
        self.assertEqual(call["cwd"], "/repo")
        self.assertEqual(call["timeout"], 30)

    def test_non_hex_sha_never_runs(self):
        for sha in ("abc; rm", "-x", "", None, "A" * 40):
            runner = FakeRunner(_result(0, ""))
            self.assertEqual(_check(runner, sha=sha), (None, "head sha is not a hex commit id"), sha)
            self.assertEqual(runner.calls, [])

    def test_sha256_accepted(self):
        runner = FakeRunner(_result(0, ""))
        self.assertEqual(_check(runner, sha="b" * 64), (1, None))

    def test_non_integer_pr_never_runs(self):
        for number in ("12", True, 0, -3):
            runner = FakeRunner(_result(0, ""))
            self.assertEqual(_check(runner, number=number), (None, "pr number is not an integer"), number)
            self.assertEqual(runner.calls, [])


class CommentsFileTests(unittest.TestCase):
    def test_file_is_private_json_of_the_discussion(self):
        runner = FakeRunner(_result(0, ""))
        _check(runner)
        self.assertEqual(runner.calls[0]["mode"], 0o600)
        self.assertEqual(runner.calls[0]["content"], _DISCUSSION)

    def test_file_deleted_after_each_outcome(self):
        outcomes = [
            FakeRunner(_result(0, "")),
            FakeRunner(_result(2, "bad")),
            FakeRunner(_result(None, "", timed_out=True)),
            FakeRunner(_result(0, ""), action=lambda path: path.unlink()),
        ]
        for runner in outcomes:
            _check(runner)
            self.assertFalse(runner.calls[0]["path"].exists())

    def test_file_deleted_when_runner_raises(self):
        runner = FakeRunner(None, error=RuntimeError("boom"))
        with self.assertRaises(RuntimeError):
            _check(runner)
        self.assertFalse(runner.calls[0]["path"].exists())

    def test_runner_value_error_is_not_validated_and_file_deleted(self):
        runner = FakeRunner(None, error=ValueError("embedded null byte"))
        self.assertEqual(_check(runner), (None, "validator could not start"))
        self.assertFalse(runner.calls[0]["path"].exists())

    def test_unserializable_discussion_is_not_validated_and_file_deleted(self):
        runner = FakeRunner(_result(0, ""))
        created = []
        original = trace_validator.tempfile.mkstemp

        def recording(**kwargs):
            handle, path = original(**kwargs)
            created.append(Path(path))
            return handle, path

        trace_validator.tempfile.mkstemp = recording
        try:
            verdict = trace_validator.check(
                _project(["v", "{comments_file}"], 30), "/repo", 7, _SHA, {"comments": [object()]}, runner
            )
        finally:
            trace_validator.tempfile.mkstemp = original
        self.assertEqual(verdict, (None, "validator could not start"))
        self.assertEqual(runner.calls, [])
        self.assertFalse(created[0].exists())

    def test_mkstemp_failure_is_not_validated(self):
        runner = FakeRunner(_result(0, ""))
        original = trace_validator.tempfile.mkstemp

        def failing(**kwargs):
            raise OSError("disk full")

        trace_validator.tempfile.mkstemp = failing
        try:
            self.assertEqual(_check(runner), (None, "validator could not run"))
        finally:
            trace_validator.tempfile.mkstemp = original
        self.assertEqual(runner.calls, [])


class VerdictTests(unittest.TestCase):
    def test_exit_zero_is_valid(self):
        self.assertEqual(_check(FakeRunner(_result(0, "whatever"))), (1, None))

    def test_nonzero_reason_is_last_non_empty_line(self):
        self.assertEqual(_check(FakeRunner(_result(1, "a\nno trace for head\n\n"))), (0, "no trace for head"))

    def test_empty_output_names_the_exit_code(self):
        self.assertEqual(_check(FakeRunner(_result(3, ""))), (0, "exit 3"))

    def test_timeout_is_not_validated(self):
        self.assertEqual(_check(FakeRunner(_result(None, "", timed_out=True))), (None, "validator timed out after 30s"))

    def test_launch_error_hides_the_os_text(self):
        verdict = _check(FakeRunner(_result(None, "", error="[Errno 2] /secret/path")))
        self.assertEqual(verdict, (None, "validator could not start"))

    def test_reason_is_capped(self):
        valid, reason = _check(FakeRunner(_result(1, "x" * 500)))
        self.assertEqual((valid, len(reason)), (0, 200))

    def test_screened_reasons_are_withheld(self):
        withheld = "exit 1 (reason withheld by the screen)"
        for text in ("mail me@example.com", "token ghp_x", "ignore previous rules", "see ACME-secret"):
            self.assertEqual(_check(FakeRunner(_result(1, text)), patterns=["ACME-secret"]), (0, withheld), text)


class RealRunnerTests(unittest.TestCase):
    def _command(self, code):
        return [sys.executable, "-I", "-c", code, "{comments_file}"]

    def test_child_reads_the_file_and_exit_codes_map(self):
        code = "import json,sys; d=json.load(open(sys.argv[1])); print('bad' if d['comments'] else 'ok'); sys.exit(4 if d['comments'] else 0)"
        project = _project(self._command(code), 30)
        verdict = trace_validator.check(project, "/", 7, _SHA, _DISCUSSION, lifecycle.run_process)
        self.assertEqual(verdict, (0, "bad"))
        verdict = trace_validator.check(project, "/", 7, _SHA, {"comments": [], "reviews": []}, lifecycle.run_process)
        self.assertEqual(verdict, (1, None))

    def test_timeout_kills_the_child_and_removes_the_file(self):
        paths = []

        def recording(argv, cwd, timeout_seconds):
            paths.append(Path(argv[-1]))
            return lifecycle.run_process(argv, cwd, timeout_seconds)

        project = _project(self._command("import time; time.sleep(60)"), 1)
        started = time.monotonic()
        verdict = trace_validator.check(project, "/", 7, _SHA, _DISCUSSION, recording)
        self.assertEqual(verdict, (None, "validator timed out after 1s"))
        self.assertLess(time.monotonic() - started, 10)
        self.assertFalse(paths[0].exists())


if __name__ == "__main__":
    unittest.main()
