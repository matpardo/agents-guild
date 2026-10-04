import os
import sqlite3
import subprocess
from unittest import mock

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

    def _handoff_content(self):
        return (self.data_home / "guild" / "handoffs" / "alpha-g1.md").read_text()

    def test_handoff_states_lead_role_and_raids_led(self):
        self.run_cli(["raid", "join", "ci", "--until-leave", "--lead"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(["handoff", "--in-flight", "x", "--learned", "y"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        self.assertIn("you lead raid ci", self._handoff_content())

    def test_handoff_omits_role_when_not_lead(self):
        self.run_cli(["raid", "join", "ci", "--until-leave"], "sess-1", self.repo_dir)
        self.run_cli(["handoff", "--in-flight", "x", "--learned", "y"], "sess-1", self.repo_dir)
        self.assertNotIn("you lead", self._handoff_content())

    def test_prints_broadcast_reminder(self):
        code, out, err = self.run_cli(
            ["handoff", "--in-flight", "x", "--learned", "y"], "sess-1", self.repo_dir
        )
        self.assertEqual(code, 0)
        self.assertIn("note: this text is broadcast to every session", out)

    def test_rejects_in_flight_over_max_length(self):
        code, out, err = self.run_cli(
            ["handoff", "--in-flight", "x" * 4001, "--learned", "y"], "sess-1", self.repo_dir
        )
        self.assertEqual(code, 1)
        self.assertIn("exceeds the maximum length", err)

    def test_rejects_learned_over_max_length(self):
        code, out, err = self.run_cli(
            ["handoff", "--in-flight", "x", "--learned", "y" * 4001], "sess-1", self.repo_dir
        )
        self.assertEqual(code, 1)
        self.assertIn("exceeds the maximum length", err)

    def test_rejects_email_in_in_flight(self):
        code, out, err = self.run_cli(
            ["handoff", "--in-flight", "ping jane.doe@example.com", "--learned", "y"],
            "sess-1", self.repo_dir,
        )
        self.assertEqual(code, 1)
        self.assertIn("must not contain an email address", err)

    def test_writes_handoff_file_and_prints_resume_command(self):
        code, out, err = self.run_cli(
            ["handoff", "--in-flight", "shipping T01", "--learned", "ci flakes on retries"],
            "sess-1", self.repo_dir,
        )
        self.assertEqual(code, 0)
        self.assertIn("GUILD_RESUME=alpha claude -n alpha-g2", out)

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

    def test_defense_in_depth_rejects_handoff_path_escaping_handoffs_dir(self):
        malicious_binding = {"party": "../../tmp/evil", "generation": 1, "project": "acme"}
        with mock.patch("guild.identity.require_binding", return_value=malicious_binding):
            code, out, err = self.run_cli(
                ["handoff", "--in-flight", "x", "--learned", "y"], "sess-1", self.repo_dir
            )
        self.assertEqual(code, 1)
        self.assertIn("escapes", err)
        escaped_path = self.data_home / "tmp" / "evil-g1.md"
        self.assertFalse(escaped_path.exists())


if __name__ == "__main__":
    import unittest

    unittest.main()


class ResumeCommandShellTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha"], "sess-1", self.repo_dir)

    def test_printed_command_runs_nothing_and_passes_prompt_intact(self):
        code, out, err = self.run_cli(
            ["handoff", "--in-flight", "x", "--learned", "y"], "sess-1", self.repo_dir
        )
        command = out.splitlines()[0]
        marker = self.root / "executed"
        script = 'guild() {{ touch "{}"; }}; claude() {{ printf "%s\\n" "$GUILD_RESUME" "$@"; }}; {}'.format(
            marker, command
        )
        result = subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=True)
        self.assertFalse(marker.exists())
        self.assertEqual(
            result.stdout.splitlines(),
            ["alpha", "-n", "alpha-g2", "Continue the work described in the guild brief."],
        )


class ResumeModelFlagTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha"], "sess-1", self.repo_dir)

    def test_model_flag_is_appended_to_resume_command(self):
        code, out, err = self.run_cli(
            ["handoff", "--in-flight", "x", "--learned", "y", "--model", "opus"],
            "sess-1", self.repo_dir,
        )
        self.assertEqual(code, 0)
        self.assertIn("claude -n alpha-g2 --model opus 'Continue", out.splitlines()[0])

    def test_resume_command_has_no_model_without_flag(self):
        code, out, err = self.run_cli(
            ["handoff", "--in-flight", "x", "--learned", "y"], "sess-1", self.repo_dir
        )
        self.assertNotIn("--model", out)


class AutoResumeTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha"], "sess-1", self.repo_dir)
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", self.repo_dir)
        self.run_cli(["task", "add", "demo/T01", "--title", "First"], "sess-1", self.repo_dir)

    def _session_start(self, session_id, resume_party):
        with mock.patch.dict(os.environ, {"GUILD_RESUME": resume_party}):
            return self.run_hook("session-start", {"session_id": session_id, "cwd": str(self.repo_dir)})

    def test_awaiting_party_is_bound_and_handoff_injected_once(self):
        self.run_cli(["handoff", "--in-flight", "shipping T01", "--learned", "retries flake"], "sess-1", self.repo_dir)
        code, out, err = self._session_start("sess-2", "alpha")
        self.assertEqual(code, 0)
        self.assertIn("party 'alpha' resumed, generation 2", out)
        self.assertEqual(out.count("shipping T01"), 1)
        self.assertIn("task demo/T01", out)
        code, out, err = self.run_cli(["whoami"], "sess-2", self.repo_dir)
        self.assertIn("alpha", out)

    def test_active_party_is_not_taken_over(self):
        code, out, err = self._session_start("sess-2", "alpha")
        self.assertEqual(code, 0)
        self.assertIn("GUILD_RESUME=alpha not applied: party is active", out)
        code, out, err = self.run_cli(["whoami"], "sess-1", self.repo_dir)
        self.assertIn("alpha", out)

    def test_session_already_leading_the_party_is_left_alone(self):
        self.run_cli(["handoff", "--in-flight", "x", "--learned", "y"], "sess-1", self.repo_dir)
        self._session_start("sess-2", "alpha")
        code, out, err = self._session_start("sess-2", "alpha")
        self.assertEqual(code, 0)
        self.assertNotIn("not applied", out)
        self.assertNotIn("generation 3", out)

    def test_invalid_party_name_is_reported(self):
        code, out, err = self._session_start("sess-2", "../x")
        self.assertEqual(code, 0)
        self.assertIn("GUILD_RESUME=../x not applied", out)
