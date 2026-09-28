import sqlite3

from tests.testutil import GuildTestCase


class HandoffTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha"], "sess-1", self.repo_dir)
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", self.repo_dir)
        self.run_cli(["task", "add", "demo/T01", "--title", "First"], "sess-1", self.repo_dir)

    def _leader_row(self):
        conn = sqlite3.connect(str(self.data_home / "guild" / "guild.db"))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM leaders WHERE party = 'alpha' ORDER BY generation DESC LIMIT 1"
        ).fetchone()
        conn.close()
        return row

    def test_rejects_empty_in_flight(self):
        code, out, err = self.run_cli(
            ["handoff", "--in-flight", "  ", "--learned", "x"], "sess-1", self.repo_dir
        )
        self.assertEqual(code, 1)
        self.assertIn("--in-flight", err)

    def test_rejects_empty_learned(self):
        code, out, err = self.run_cli(
            ["handoff", "--in-flight", "x", "--learned", ""], "sess-1", self.repo_dir
        )
        self.assertEqual(code, 1)
        self.assertIn("--learned", err)

    def test_writes_handoff_file_and_prints_resume_command(self):
        code, out, err = self.run_cli(
            ["handoff", "--in-flight", "shipping T01", "--learned", "ci flakes on retries"],
            "sess-1", self.repo_dir,
        )
        self.assertEqual(code, 0)
        self.assertIn("claude -n alpha-g2", out)
        self.assertIn("guild party resume alpha", out)

        handoff_path = self.data_home / "guild" / "handoffs" / "alpha-g1.md"
        self.assertTrue(handoff_path.is_file())
        content = handoff_path.read_text()
        self.assertIn("demo — Demo", content)
        self.assertIn("shipping T01", content)
        self.assertIn("ci flakes on retries", content)

    def test_party_state_becomes_awaiting_leader(self):
        self.run_cli(
            ["handoff", "--in-flight", "x", "--learned", "y"], "sess-1", self.repo_dir
        )
        code, out, err = self.run_cli(["board"], None, None)
        self.assertIn("awaiting-leader", out)

    def test_leader_handoff_path_recorded(self):
        self.run_cli(
            ["handoff", "--in-flight", "x", "--learned", "y"], "sess-1", self.repo_dir
        )
        row = self._leader_row()
        self.assertTrue(row["handoff_path"].endswith("alpha-g1.md"))

    def test_handoff_includes_next_queue(self):
        self.write_gh_fixture(
            "view_acme-app_1",
            {
                "state": "OPEN", "isDraft": True, "headRefName": "feature/x", "title": "t",
                "statusCheckRollup": [{"conclusion": "FAILURE"}],
            },
        )
        self.run_cli(
            ["pr", "track", "acme/app#1", "--task", "demo/T01", "--what", "x", "--waits", "y"],
            "sess-1", self.repo_dir,
        )
        self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)
        self.run_cli(
            ["handoff", "--in-flight", "x", "--learned", "y"], "sess-1", self.repo_dir
        )
        content = (self.data_home / "guild" / "handoffs" / "alpha-g1.md").read_text()
        self.assertIn("failing checks", content)


if __name__ == "__main__":
    import unittest

    unittest.main()
