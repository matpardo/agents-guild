import unittest
from datetime import timedelta
from unittest import mock

from guild import db, events, paths, timeutil
from guild.cli import build_parser
from tests import resources_fixtures as fixtures
from tests.testutil import GuildTestCase

_GB = 1000000000
_MACHINE = {
    "disk_total": 500 * _GB,
    "disk_used": 400 * _GB,
    "mem_total": 31 * _GB,
    "mem_available": 9 * _GB,
    "guild_db_bytes": 1000,
    "docker": None,
}


class ResourcesParserTests(unittest.TestCase):
    def setUp(self):
        self.parser = build_parser()

    def test_bare_resources_is_the_report_with_default_window(self):
        args = self.parser.parse_args(["resources"])
        self.assertIsNone(args.resources_action)
        self.assertEqual(args.since, "1d")
        self.assertIsNone(args.project)

    def test_report_options(self):
        args = self.parser.parse_args(["resources", "--project", "acme", "--since", "3d"])
        self.assertIsNone(args.resources_action)
        self.assertEqual((args.project, args.since), ("acme", "3d"))

    def test_collect_action(self):
        args = self.parser.parse_args(["resources", "collect"])
        self.assertEqual(args.resources_action, "collect")

    def test_unknown_action_is_rejected(self):
        with self.assertRaises(SystemExit):
            with mock.patch("sys.stderr"):
                self.parser.parse_args(["resources", "wipe"])


class ResourcesCliTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        fixtures.init_clone(self.repo_dir, "acme/app")

    def _seed(self, project, when, size):
        conn = db.connect(paths.db_path())
        with db.writing(conn):
            events.record(
                conn,
                when,
                "tester@host",
                None,
                None,
                project,
                "resources.sampled",
                "local",
                {"items": [["worktree", "/home/u/acme/app", size, "ok", "", "main"]], "machine": _MACHINE},
            )
        conn.close()

    def test_report_without_samples_says_so_and_exits_zero(self):
        code, out, err = self.run_cli(["resources"], None, self.repo_dir)
        self.assertEqual(code, 0, err)
        self.assertEqual(out, "no samples yet; run guild resources collect\n")

    def test_report_prints_the_machine_and_project_blocks(self):
        now = timeutil.utcnow()
        self._seed("acme", now - timedelta(days=2), 3 * _GB)
        self._seed("acme", now - timedelta(minutes=5), 5 * _GB)
        code, out, err = self.run_cli(["resources", "--since", "1d"], None, self.repo_dir)
        self.assertEqual(code, 0, err)
        self.assertIn("machine   disk 80% used", out)
        self.assertIn("acme   total 5.0 GB (+2.0 GB)", out)
        self.assertIn("/home/u/acme/app", out)

    def test_report_filters_by_project(self):
        now = timeutil.utcnow()
        self._seed("acme", now - timedelta(minutes=5), 5 * _GB)
        code, out, err = self.run_cli(["resources", "--project", "acme"], None, self.repo_dir)
        self.assertEqual(code, 0, err)
        self.assertIn("acme   total 5.0 GB", out)
        self.assertNotIn("unattributed", out)

    def test_unknown_project_exits_one(self):
        code, out, err = self.run_cli(["resources", "--project", "nope"], None, self.repo_dir)
        self.assertEqual(code, 1)
        self.assertIn("unknown project 'nope'", err)

    def test_invalid_since_exits_one(self):
        code, out, err = self.run_cli(["resources", "--since", "soon"], None, self.repo_dir)
        self.assertEqual(code, 1)
        self.assertIn("invalid duration", err)

    def test_report_does_not_write_any_event(self):
        now = timeutil.utcnow()
        self._seed("acme", now - timedelta(minutes=5), 5 * _GB)
        conn = db.connect(paths.db_path())
        before = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        conn.close()
        self.run_cli(["resources"], None, self.repo_dir)
        conn = db.connect(paths.db_path())
        after = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        conn.close()
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
