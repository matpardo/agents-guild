from datetime import timedelta
from unittest import mock

from guild import timeutil
from tests.testutil import GuildTestCase


class NoticeTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])

    def test_create_requires_valid_to(self):
        code, out, err = self.run_cli(["notice", "create", "hi", "--to", "weird", "--ttl", "1h"], None, None)
        self.assertEqual(code, 1)
        self.assertIn("invalid --to", err)

    def test_create_rejects_unknown_project_scope(self):
        code, out, err = self.run_cli(["notice", "create", "hi", "--to", "project:ghost", "--ttl", "1h"], None, None)
        self.assertEqual(code, 1)

    def test_create_rejects_path_traversal_project_scope(self):
        code, out, err = self.run_cli(
            ["notice", "create", "hi", "--to", "project:../../tmp/x", "--ttl", "1h"], None, None
        )
        self.assertEqual(code, 1)
        self.assertIn("invalid", err)

    def test_create_prints_broadcast_reminder(self):
        code, out, err = self.run_cli(["notice", "create", "pipeline down", "--to", "guild", "--ttl", "2h"], None, None)
        self.assertEqual(code, 0)
        self.assertIn("note: this text is broadcast to every session", out)

    def test_success_reminder_does_not_look_like_an_error(self):
        code, out, err = self.run_cli(["notice", "create", "ci down", "--to", "guild", "--ttl", "1h"], None, None)
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        for line in out.splitlines():
            self.assertFalse(line.startswith("guild:"), line)
        self.assertIn("note:", out)

    def test_duplicate_active_notice_from_same_actor_is_rejected(self):
        self.run_cli(["notice", "create", "ci down", "--to", "guild", "--ttl", "1h"], None, None)
        code, out, err = self.run_cli(["notice", "create", "ci down", "--to", "guild", "--ttl", "1h"], None, None)
        self.assertEqual(code, 1)
        self.assertIn("already active as notice #1", err)
        code, out, err = self.run_cli(["notices"], None, None)
        self.assertEqual(len([line for line in out.splitlines() if "ci down" in line]), 1)

    def test_same_text_allowed_after_previous_notice_closed(self):
        self.run_cli(["notice", "create", "ci down", "--to", "guild", "--ttl", "1h"], None, None)
        self.run_cli(["notice", "close", "1"], None, None)
        code, out, err = self.run_cli(["notice", "create", "ci down", "--to", "guild", "--ttl", "1h"], None, None)
        self.assertEqual(code, 0)

    def test_create_rejects_text_over_max_length(self):
        code, out, err = self.run_cli(["notice", "create", "x" * 501, "--to", "guild", "--ttl", "2h"], None, None)
        self.assertEqual(code, 1)
        self.assertIn("exceeds the maximum length", err)

    def test_create_rejects_email_address(self):
        code, out, err = self.run_cli(
            ["notice", "create", "contact jane.doe@example.com", "--to", "guild", "--ttl", "2h"],
            None,
            None,
        )
        self.assertEqual(code, 1)
        self.assertIn("must not contain an email address", err)

    def test_create_rejects_text_matching_project_pii_pattern(self):
        config_file = self.config_home / "guild" / "projects" / "acme.json"
        import json

        data = json.loads(config_file.read_text())
        data["pii_patterns"] = [r"Jane Doe"]
        config_file.write_text(json.dumps(data))
        code, out, err = self.run_cli(
            ["notice", "create", "customer Jane Doe missed a payment", "--to", "project:acme", "--ttl", "2h"],
            None,
            self.repo_dir,
        )
        self.assertEqual(code, 1)
        self.assertIn("forbidden", err)
        self.assertNotIn("Jane Doe", err)

    def test_create_strips_escape_sequences_from_text(self):
        code, out, err = self.run_cli(
            ["notice", "create", "hi\x1b[31mRED\x1b[0m", "--to", "guild", "--ttl", "1h"], None, None
        )
        self.assertEqual(code, 0)
        code, out, err = self.run_cli(["notices"], None, None)
        self.assertIn("hiRED", out)
        self.assertNotIn("\x1b", out)

    def test_create_and_list_guild_scope(self):
        code, out, err = self.run_cli(["notice", "create", "pipeline down", "--to", "guild", "--ttl", "2h"], None, None)
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
        code, out, err = self.run_cli(["notice", "create", "short lived", "--to", "guild", "--ttl", "30m"], None, None)
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
