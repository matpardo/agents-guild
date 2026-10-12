import json
import os
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from guild import pii
from guild.cli import _build_context
from guild.commands import handoff as handoff_commands
from guild.commands import memory as memory_commands
from guild.errors import GuildError
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

    def test_learned_text_joins_party_memory(self):
        self.run_cli(
            ["handoff", "--in-flight", "x", "--learned", "something new"], "sess-1", self.repo_dir
        )
        items = memory_commands.list_items("alpha")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["text"], "something new")

    def test_repeating_learned_text_is_deduped_in_memory(self):
        self.run_cli(["handoff", "--in-flight", "x", "--learned", "same"], "sess-1", self.repo_dir)
        self.run_cli(["party", "resume", "alpha"], "sess-1", self.repo_dir)
        self.run_cli(["handoff", "--in-flight", "x", "--learned", "same"], "sess-1", self.repo_dir)
        self.assertEqual(len(memory_commands.list_items("alpha")), 1)

    def test_different_learned_text_adds_a_second_memory_item_newest_first(self):
        self.run_cli(["handoff", "--in-flight", "x", "--learned", "first"], "sess-1", self.repo_dir)
        self.run_cli(["party", "resume", "alpha"], "sess-1", self.repo_dir)
        self.run_cli(["handoff", "--in-flight", "x", "--learned", "second"], "sess-1", self.repo_dir)
        items = memory_commands.list_items("alpha")
        self.assertEqual([item["text"] for item in items], ["second", "first"])

    def test_learned_text_over_memory_cap_is_trimmed_in_memory_but_full_in_handoff_file(self):
        learned = "y" * 1000
        self.run_cli(["handoff", "--in-flight", "x", "--learned", learned], "sess-1", self.repo_dir)
        content = (self.data_home / "guild" / "handoffs" / "alpha-g1.md").read_text()
        self.assertIn(learned, content)
        items = memory_commands.list_items("alpha")
        stored = items[0]["text"]
        self.assertEqual(len(stored), pii.MEMORY_ITEM_MAX_LENGTH)
        self.assertEqual(stored, "y" * (pii.MEMORY_ITEM_MAX_LENGTH - 1) + "…")

    def test_rejects_email_in_learned_before_writing_handoff_or_memory(self):
        code, out, err = self.run_cli(
            ["handoff", "--in-flight", "x", "--learned", "ping jane.doe@example.com"],
            "sess-1", self.repo_dir,
        )
        self.assertEqual(code, 1)
        self.assertIn("must not contain an email address", err)
        self.assertFalse((self.data_home / "guild" / "handoffs" / "alpha-g1.md").exists())
        self.assertEqual(memory_commands.list_items("alpha"), [])

    def test_defense_in_depth_rejects_handoff_path_escaping_handoffs_dir(self):
        malicious_binding = {"party": "../../tmp/evil", "generation": 1, "project": "acme"}
        with mock.patch("guild.identity.require_binding", return_value=malicious_binding):
            code, out, err = self.run_cli(
                ["handoff", "--in-flight", "x", "--learned", "y"], "sess-1", self.repo_dir
            )
        self.assertEqual(code, 1)
        self.assertIn("invalid party name", err)
        escaped_path = self.data_home / "tmp" / "evil-g1.md"
        self.assertFalse(escaped_path.exists())
        self.assertEqual(list((self.data_home / "guild" / "memory").iterdir()), [])


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


def _init_git_repo(root):
    remote_dir = root / "remote"
    remote_dir.mkdir()
    for command in (
        ["git", "init", "-q", "-b", "main"],
        ["git", "config", "user.email", "t@t.com"],
        ["git", "config", "user.name", "t"],
        ["git", "commit", "--allow-empty", "-q", "-m", "init"],
    ):
        subprocess.run(command, cwd=str(remote_dir), check=True)
    work_dir = root / "work"
    subprocess.run(["git", "clone", "-q", str(remote_dir), str(work_dir)], check=True)
    return work_dir


class AutoInFlightGitTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _commit(self, repo_dir, message):
        subprocess.run(["git", "commit", "--allow-empty", "-q", "-m", message], cwd=str(repo_dir), check=True)

    def test_clean_repo_with_upstream_is_all_zero(self):
        repo_dir = _init_git_repo(self.root)
        self.assertEqual(
            handoff_commands._auto_in_flight(repo_dir),
            "automatic handoff: branch main, 0 uncommitted, 0 unpushed",
        )

    def test_dirty_worktree_counts_uncommitted(self):
        repo_dir = _init_git_repo(self.root)
        (repo_dir / "untracked.txt").write_text("x")
        self.assertIn("1 uncommitted", handoff_commands._auto_in_flight(repo_dir))

    def test_local_commits_ahead_count_unpushed(self):
        repo_dir = _init_git_repo(self.root)
        self._commit(repo_dir, "one")
        self._commit(repo_dir, "two")
        self.assertIn("2 unpushed", handoff_commands._auto_in_flight(repo_dir))

    def test_no_upstream_configured_reports_unpushed_unknown(self):
        repo_dir = self.root / "solo"
        repo_dir.mkdir()
        for command in (
            ["git", "init", "-q", "-b", "main"],
            ["git", "config", "user.email", "t@t.com"],
            ["git", "config", "user.name", "t"],
            ["git", "commit", "--allow-empty", "-q", "-m", "init"],
        ):
            subprocess.run(command, cwd=str(repo_dir), check=True)
        self.assertIn("unpushed unknown", handoff_commands._auto_in_flight(repo_dir))

    def test_detached_head_reports_branch_unknown(self):
        repo_dir = _init_git_repo(self.root)
        subprocess.run(["git", "checkout", "-q", "--detach"], cwd=str(repo_dir), check=True)
        self.assertIn("branch unknown", handoff_commands._auto_in_flight(repo_dir))

    def test_non_git_directory_reports_worktree_unknown(self):
        plain_dir = self.root / "plain"
        plain_dir.mkdir()
        self.assertEqual(handoff_commands._auto_in_flight(plain_dir), "automatic handoff: worktree unknown")

    def test_none_cwd_reports_worktree_unknown_without_crashing(self):
        self.assertEqual(handoff_commands._auto_in_flight(None), "automatic handoff: worktree unknown")


class WriteAutoTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        for command in (
            ["git", "init", "-q", "-b", "main"],
            ["git", "config", "user.email", "t@t.com"],
            ["git", "config", "user.name", "t"],
            ["git", "commit", "--allow-empty", "-q", "-m", "init"],
        ):
            subprocess.run(command, cwd=str(self.repo_dir), check=True)
        self.run_cli(["party", "start", "alpha"], "sess-1", self.repo_dir)

    def _binding(self):
        return {"party": "alpha", "project": "acme", "generation": 1}

    def _write(self):
        ctx = _build_context(None, None)
        handoff_commands.write_auto(ctx, self._binding())

    def _handoff_content(self):
        return (self.data_home / "guild" / "handoffs" / "alpha-g1.md").read_text()

    def test_learned_is_the_fixed_automatic_string(self):
        self._write()
        content = self._handoff_content()
        self.assertIn("## Learned\nnone (automatic handoff)", content)

    def test_in_flight_carries_the_git_summary(self):
        self._write()
        content = self._handoff_content()
        self.assertIn("## In flight\nautomatic handoff: branch main,", content)

    def test_records_an_auto_handed_off_event(self):
        self._write()
        conn = sqlite3.connect(str(self.data_home / "guild" / "guild.db"))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT payload FROM events WHERE kind = 'party.handed_off' ORDER BY seq DESC LIMIT 1"
        ).fetchone()
        conn.close()
        self.assertTrue(json.loads(row["payload"])["auto"])

    def test_does_not_create_a_party_memory_item(self):
        self._write()
        self.assertEqual(memory_commands.list_items("alpha"), [])
        self.assertEqual(list((self.data_home / "guild" / "memory").iterdir()), [])


class RunForPartyTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha"], "sess-1", self.repo_dir)

    def _party_state(self):
        conn = sqlite3.connect(str(self.data_home / "guild" / "guild.db"))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT state FROM parties WHERE name = 'alpha'").fetchone()
        conn.close()
        return row["state"]

    def test_unknown_party_raises(self):
        ctx = _build_context(None, None)
        with self.assertRaises(GuildError):
            handoff_commands.run_for_party(ctx, "nope")

    def test_closed_party_raises(self):
        self.run_cli(["party", "close", "alpha", "--force"], None, self.repo_dir)
        ctx = _build_context(None, None)
        with self.assertRaises(GuildError) as raised:
            handoff_commands.run_for_party(ctx, "alpha")
        self.assertIn("closed", raised.exception.message)

    def test_party_with_a_live_leader_raises(self):
        self.write_session(os.getpid(), "sess-1", "alpha-g1")
        ctx = _build_context(None, None)
        with self.assertRaises(GuildError) as raised:
            handoff_commands.run_for_party(ctx, "alpha")
        self.assertIn("has a live leader", raised.exception.message)

    def test_party_with_no_live_leader_succeeds_and_becomes_awaiting_leader(self):
        ctx = _build_context(None, None)
        message = handoff_commands.run_for_party(ctx, "alpha")
        self.assertIn("alpha", message)
        self.assertEqual(self._party_state(), "awaiting-leader")


class HandoffCliPartyFlagTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha"], "sess-1", self.repo_dir)

    def test_party_rejects_combination_with_every_other_handoff_flag(self):
        cases = (
            (["handoff", "prune", "--party", "alpha"], "prune"),
            (["handoff", "--party", "alpha", "--in-flight", "x"], "--in-flight"),
            (["handoff", "--party", "alpha", "--learned", "y"], "--learned"),
            (["handoff", "--party", "alpha", "--model", "opus"], "--model"),
            (["handoff", "--party", "alpha", "--dry-run"], "--dry-run"),
            (["handoff", "--party", "alpha", "--respawn"], "--respawn"),
            (["handoff", "--party", "alpha", "--close"], "--close"),
        )
        for argv, flag in cases:
            with self.subTest(flag=flag):
                code, out, err = self.run_cli(argv, None, self.repo_dir)
                self.assertEqual(code, 1)
                self.assertIn(flag, err)

    def test_party_from_a_bound_session_is_rejected(self):
        code, out, err = self.run_cli(["handoff", "--party", "alpha"], "sess-1", self.repo_dir)
        self.assertEqual(code, 1)
        self.assertIn("cannot be used from inside a Claude Code session", err)

    def test_party_from_no_session_with_no_live_leader_succeeds(self):
        code, out, err = self.run_cli(["handoff", "--party", "alpha"], None, self.repo_dir)
        self.assertEqual(code, 0)
        self.assertIn("handoff written for 'alpha'", out)
