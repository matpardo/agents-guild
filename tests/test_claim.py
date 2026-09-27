from datetime import timedelta
from unittest import mock

from guild import timeutil
from tests.testutil import GuildTestCase


class ClaimTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha"], "sess-1", self.repo_dir)

    def test_claim_and_list(self):
        code, out, err = self.run_cli(["claim", "ci.yml", "--ttl", "30m"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0)
        code, out, err = self.run_cli(["claims"], "sess-1", self.repo_dir)
        self.assertIn("ci.yml — alpha", out)

    def test_conflicting_claim_from_other_party_blocked(self):
        self.run_cli(["claim", "ci.yml", "--ttl", "30m"], "sess-1", self.repo_dir)
        self.run_cli(["party", "start", "beta"], "sess-2", self.repo_dir)
        code, out, err = self.run_cli(["claim", "ci.yml", "--ttl", "30m"], "sess-2", self.repo_dir)
        self.assertEqual(code, 1)
        self.assertIn("claimed by party 'alpha'", err)

    def test_same_party_refreshes_claim(self):
        self.run_cli(["claim", "ci.yml", "--ttl", "30m"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["claim", "ci.yml", "--ttl", "8h"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0)

    def test_expired_claim_can_be_taken_by_other_party(self):
        self.run_cli(["claim", "ci.yml", "--ttl", "30m"], "sess-1", self.repo_dir)
        self.run_cli(["party", "start", "beta"], "sess-2", self.repo_dir)
        future = timeutil.utcnow() + timedelta(hours=1)
        with mock.patch("guild.timeutil.utcnow", return_value=future):
            code, out, err = self.run_cli(["claim", "ci.yml", "--ttl", "30m"], "sess-2", self.repo_dir)
        self.assertEqual(code, 0)

    def test_release_requires_holder(self):
        self.run_cli(["claim", "ci.yml", "--ttl", "30m"], "sess-1", self.repo_dir)
        self.run_cli(["party", "start", "beta"], "sess-2", self.repo_dir)
        code, out, err = self.run_cli(["release", "ci.yml"], "sess-2", self.repo_dir)
        self.assertEqual(code, 1)
        self.assertIn("does not hold claim", err)

    def test_release_by_holder(self):
        self.run_cli(["claim", "ci.yml", "--ttl", "30m"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["release", "ci.yml"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0)
        code, out, err = self.run_cli(["claims"], "sess-1", self.repo_dir)
        self.assertEqual(out, "")


if __name__ == "__main__":
    import unittest

    unittest.main()
