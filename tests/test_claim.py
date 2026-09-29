import json
import sqlite3
from datetime import timedelta
from unittest import mock

from guild import db, origin, paths, timeutil
from guild.commands import claim as claim_commands
from guild.context import RunContext
from tests.testutil import GuildTestCase


class ClaimTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha"], "sess-1", self.repo_dir)

    def _last_claim_created_payload(self):
        conn = sqlite3.connect(str(self.data_home / "guild" / "guild.db"))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT payload FROM events WHERE kind = 'claim.created' ORDER BY seq DESC LIMIT 1"
        ).fetchone()
        conn.close()
        return json.loads(row["payload"])

    def test_claim_records_claimed_by_agent_when_given(self):
        ctx = RunContext(
            db.connect(paths.db_path()),
            "sess-1",
            self.repo_dir,
            timeutil.utcnow(),
            origin.current_origin(),
            None,
            self.config_home / "guild" / "projects",
            None,
        )
        claim_commands.claim(ctx, "area:config/routes.rb", "2h", "coder")
        payload = self._last_claim_created_payload()
        self.assertEqual(payload["claimed_by_agent"], "coder")

    def test_claim_omits_claimed_by_agent_when_not_given(self):
        ctx = RunContext(
            db.connect(paths.db_path()),
            "sess-1",
            self.repo_dir,
            timeutil.utcnow(),
            origin.current_origin(),
            None,
            self.config_home / "guild" / "projects",
            None,
        )
        claim_commands.claim(ctx, "ci.yml", "30m", None)
        payload = self._last_claim_created_payload()
        self.assertNotIn("claimed_by_agent", payload)

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

    def test_claim_by_task_ref_accepted(self):
        code, out, err = self.run_cli(["claim", "task:demo/T01", "--ttl", "30m"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0)
        code, out, err = self.run_cli(["claims"], "sess-1", self.repo_dir)
        self.assertIn("task:demo/T01 — alpha", out)

    def test_claim_by_task_ref_rejects_malformed_ref(self):
        code, out, err = self.run_cli(["claim", "task:no-slash-here", "--ttl", "30m"], "sess-1", self.repo_dir)
        self.assertEqual(code, 1)
        self.assertIn("invalid task ref", err)

    def test_release_by_holder(self):
        self.run_cli(["claim", "ci.yml", "--ttl", "30m"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["release", "ci.yml"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0)
        code, out, err = self.run_cli(["claims"], "sess-1", self.repo_dir)
        self.assertEqual(out, "")

    def test_claim_by_area_prefixed_string_accepted(self):
        code, out, err = self.run_cli(
            ["claim", "area:config/routes.rb", "--ttl", "2h"], "sess-1", self.repo_dir
        )
        self.assertEqual(code, 0)
        code, out, err = self.run_cli(["claims"], "sess-1", self.repo_dir)
        self.assertIn("area:config/routes.rb — alpha", out)


if __name__ == "__main__":
    import unittest

    unittest.main()
