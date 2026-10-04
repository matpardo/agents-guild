import io
import tempfile
import unittest
from pathlib import Path

from tests import run_parallel

_PASSING = "import unittest\n\n\nclass T(unittest.TestCase):\n    def test_a(self):\n        pass\n\n    def test_b(self):\n        pass\n"
_FAILING = "import unittest\n\n\nclass T(unittest.TestCase):\n    def test_a(self):\n        self.fail('boom')\n"


class RunParallelTests(unittest.TestCase):
    def setUp(self):
        self._tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tempdir.cleanup)
        self.root = Path(self._tempdir.name)
        self.package = self.root / "pkg"
        self.package.mkdir()
        (self.package / "__init__.py").write_text("")

    def _write(self, name, text):
        (self.package / name).write_text(text)

    def _run(self):
        out = io.StringIO()
        code = run_parallel.run(self.root, "pkg", 2, out)
        return code, out.getvalue()

    def test_all_passing_modules_exit_zero_with_total(self):
        self._write("test_one.py", _PASSING)
        self._write("test_two.py", _PASSING)
        code, out = self._run()
        self.assertEqual(code, 0)
        self.assertIn("2 modules, 4 tests, 0 failed", out)

    def test_failing_module_exits_one_and_prints_its_output(self):
        self._write("test_one.py", _PASSING)
        self._write("test_bad.py", _FAILING)
        code, out = self._run()
        self.assertEqual(code, 1)
        self.assertIn("pkg.test_bad", out)
        self.assertIn("boom", out)
        self.assertIn("2 modules, 3 tests, 1 failed", out)

    def test_only_test_modules_are_run(self):
        self._write("test_one.py", _PASSING)
        self._write("helper.py", "raise SystemExit(3)\n")
        code, out = self._run()
        self.assertEqual(code, 0)
        self.assertIn("1 modules, 2 tests, 0 failed", out)
