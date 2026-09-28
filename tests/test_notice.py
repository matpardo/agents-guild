from datetime import timedelta
from unittest import mock

from guild import timeutil
from tests.testutil import GuildTestCase


class NoticeTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])

    def test_create_requires_valid_to(self):
        code, out, err = self.run_cli(
            ["notice", "create", "hi", "--to", "weird", "--ttl", "1h"], None, None
        )
        self.assertEqual(code, 1)
        self.assertIn("invalid --to", err)

    def test_create_rejects_unknown_project_scope(self):
        code, out, err = self.run_cli(
            ["notice", "create", "hi", "--to", "project:ghost", "--ttl", "1h"], None, None
        )
        self.assertEqual(code, 1)

    def test_create_rejects_path_traversal_project_scope(self):
        code, out, err = self.run_cli(
            ["notice", "create", "hi", "--to", "project:../../tmp/x", "--ttl", "1h"], None, None
        )
        self.assertEqual(code, 1)
        self.assertIn("invalid", err)

    def test_create_strips_escape_sequences_from_text(self):
        code, out, err = self.run_cli(
            ["notice", "create", "hi\x1b[31mRED\x1b[0m", "--to", "guild", "--ttl", "1h"], None, None
        )
        self.assertEqual(code, 0)
        code, out, err = self.run_cli(["notices"], None, None)
        self.assertIn("hiRED", out)
        self.assertNotIn("\x1b", out)

    def test_create_and_list_guild_scope(self):
        code, out, err = self.run_cli(
            ["notice", "create", "pipeline down", "--to", "guild", "--ttl", "2h"], None, None
        )
        self.assertEqual(code, 0)
        code, out, err = self.run_cli(["notices"], None, None)
        self.assertIn("pipeline down", out)

    def test_close(self):
        self.run_cli(["notice", "create", "pipeline down", "--to", "guild", "--ttl", "2h"], None, None)
        code, out, err = self.run_cli(["notice", "close", "1"], None, None)
        self.assertEqual(code, 0)
        code, out, err = self.run_cli(["notices"], None, None)
        self.assertEqual(out, "")

    def test_close_unknown_id(self):
        code, out, err = self.run_cli(["notice", "close", "99"], None, None)
        self.assertEqual(code, 1)
        self.assertIn("unknown notice", err)

    def test_expired_notice_not_listed(self):
        code, out, err = self.run_cli(
            ["notice", "create", "short lived", "--to", "guild", "--ttl", "30m"], None, None
        )
        self.assertEqual(code, 0)
        code, out, err = self.run_cli(["notices"], None, None)
        self.assertIn("short lived", out)
        future = timeutil.utcnow() + timedelta(hours=1)
        with mock.patch("guild.timeutil.utcnow", return_value=future):
            code, out, err = self.run_cli(["notices"], None, None)
        self.assertEqual(out, "")


if __name__ == "__main__":
    import unittest

    unittest.main()
