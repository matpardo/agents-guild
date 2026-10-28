import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from guild import due_jobs

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _decoy_checkout(root):
    package = root / "guild"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "__main__.py").write_text("print('DECOY GUILD')\n")
    return root


class ShimIsolationTests(unittest.TestCase):
    def test_shim_runs_its_own_repo_even_from_inside_another_checkout(self):
        with tempfile.TemporaryDirectory() as tmp:
            decoy = _decoy_checkout(Path(tmp))
            result = subprocess.run(
                [str(_REPO_ROOT / "bin" / "guild"), "--help"],
                cwd=str(decoy),
                capture_output=True,
                text=True,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("DECOY GUILD", result.stdout)
        self.assertIn("usage: guild", result.stdout)

    def test_background_sync_runs_this_repo_even_from_inside_another_checkout(self):
        with tempfile.TemporaryDirectory() as tmp:
            decoy = _decoy_checkout(Path(tmp))
            with mock.patch("subprocess.Popen") as popen:
                due_jobs.spawn_detached(("sync", "--source", "gh"), decoy, False)
            argv = popen.call_args.args[0]
            result = subprocess.run(argv[:-3] + ["--help"], cwd=str(decoy), capture_output=True, text=True)
        self.assertEqual(argv[-3:], ["sync", "--source", "gh"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("DECOY GUILD", result.stdout)
        self.assertIn("usage: guild", result.stdout)


if __name__ == "__main__":
    unittest.main()
