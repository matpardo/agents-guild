import json

from guild import db, events, paths, resume, timeutil
from guild.commands import party as party_commands
from guild.commands import statusline as statusline_commands
from tests.testutil import GuildTestCase

_PROMPT = "'Continue the work described in the guild brief.'"


class KeeperPartyTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])

    def _keeper_flag(self, party):
        conn = db.connect(paths.db_path())
        value = conn.execute("SELECT keeper FROM parties WHERE name = ?", (party,)).fetchone()["keeper"]
        conn.close()
        return value

    def _is_keeper(self, party):
        conn = db.connect(paths.db_path())
        value = party_commands.is_keeper(conn, party)
        conn.close()
        return value

    def test_start_with_keeper_flag_persists_and_prints_hint(self):
        code, out, err = self.run_cli(["party", "start", "alpha", "--keeper"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        self.assertIn("party 'alpha' started, generation 1 (keeper)", out)
        self.assertIn("close this session and run: guild revive --party alpha", out)
        self.assertEqual(self._keeper_flag("alpha"), 1)
        self.assertTrue(self._is_keeper("alpha"))

    def test_plain_start_is_not_a_keeper_and_prints_no_hint(self):
        code, out, err = self.run_cli(["party", "start", "alpha"], "sess-1", self.repo_dir)
        self.assertEqual(out.strip(), "party 'alpha' started, generation 1")
        self.assertEqual(self._keeper_flag("alpha"), 0)
        self.assertFalse(self._is_keeper("alpha"))

    def test_flag_persists_across_generations_and_rebuild(self):
        self.run_cli(["party", "start", "alpha", "--keeper"], "sess-1", self.repo_dir)
        self.run_cli(["handoff", "--in-flight", "x", "--learned", "y"], "sess-1", self.repo_dir)
        self.run_cli(["party", "resume", "alpha"], "sess-2", self.repo_dir)
        self.assertTrue(self._is_keeper("alpha"))
        self.run_cli(["rebuild"], None, None)
        self.assertTrue(self._is_keeper("alpha"))

    def test_legacy_started_event_without_key_replays_as_non_keeper(self):
        conn = db.connect(paths.db_path())
        with db.writing(conn):
            events.record(
                conn, timeutil.utcnow(), "tester@host", "legacy", "sess-9", "acme", "party.started", "local",
                {"party": "legacy", "session_name": None},
            )
        conn.close()
        self.run_cli(["rebuild"], None, None)
        self.assertEqual(self._keeper_flag("legacy"), 0)


class RemoteControlCommandTests(GuildTestCase):
    def test_resume_command_for_keeper(self):
        self.assertEqual(
            resume.resume_command("sess-1", "alpha", 3, "acceptEdits", True),
            "claude --resume sess-1 --name alpha-g3 --permission-mode acceptEdits --remote-control alpha-g3",
        )
        self.assertEqual(
            resume.resume_command("sess-1", "alpha", 3, None, True),
            "claude --resume sess-1 --name alpha-g3 --remote-control alpha-g3",
        )

    def test_resume_command_for_non_keeper_is_unchanged(self):
        self.assertEqual(
            resume.resume_command("sess-1", "alpha", 3, "plan", False),
            "claude --resume sess-1 --name alpha-g3 --permission-mode plan",
        )

    def test_fresh_command_for_keeper_puts_remote_control_right_before_prompt(self):
        self.assertEqual(
            resume.fresh_command("alpha", 4, "opus", "plan", True, resume.RESUME_PROMPT),
            "GUILD_RESUME=alpha claude -n alpha-g4 --model opus --permission-mode plan"
            " --remote-control alpha-g4 " + _PROMPT,
        )

    def test_fresh_command_for_non_keeper_is_unchanged(self):
        self.assertEqual(
            resume.fresh_command("alpha", 4, None, None, False, resume.RESUME_PROMPT),
            "GUILD_RESUME=alpha claude -n alpha-g4 " + _PROMPT,
        )


class PartyNameQuotingTests(GuildTestCase):
    def test_resume_command_quotes_generation_name_everywhere(self):
        self.assertEqual(
            resume.resume_command("sess-1", "a b", 3, None, True),
            "claude --resume sess-1 --name 'a b-g3' --remote-control 'a b-g3'",
        )

    def test_fresh_command_quotes_party_everywhere(self):
        self.assertEqual(
            resume.fresh_command("a b", 4, None, None, True, resume.RESUME_PROMPT),
            "GUILD_RESUME='a b' claude -n 'a b-g4' --remote-control 'a b-g4' " + _PROMPT,
        )

    def test_fresh_command_without_remote_control_quotes_party(self):
        self.assertTrue(
            resume.fresh_command("a;b", 2, None, None, False, resume.RESUME_PROMPT).startswith("GUILD_RESUME='a;b' claude -n 'a;b-g2' ")
        )


class KeeperSurfacesTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.work = self.repo_dir.parent / "work"
        self.work.mkdir()

    def _transcript(self, session_id):
        directory = self.claude_projects_dir / "-w"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "{}.jsonl".format(session_id)).write_text(json.dumps({"cwd": str(self.work)}) + "\n")

    def _list(self):
        code, out, err = self.run_cli(["revive", "--list"], None, None)
        self.assertEqual(code, 0, err)
        return out

    def test_revive_list_for_keeper_resume_includes_remote_control(self):
        self.run_cli(["party", "start", "alpha", "--keeper"], "sess-a", self.work)
        self._transcript("sess-a")
        self.assertIn("--name alpha-g1 --remote-control alpha-g1", self._list())

    def test_revive_list_for_keeper_fresh_includes_remote_control(self):
        self.run_cli(["party", "start", "alpha", "--keeper"], "sess-a", self.work)
        self.assertIn("claude -n alpha-g2 --remote-control alpha-g2 ", self._list())

    def test_revive_list_for_non_keeper_has_no_remote_control(self):
        self.run_cli(["party", "start", "alpha"], "sess-a", self.work)
        self._transcript("sess-a")
        self.assertNotIn("--remote-control", self._list())

    def test_handoff_output_for_keeper_includes_remote_control(self):
        self.run_cli(["party", "start", "alpha", "--keeper"], "sess-a", self.work)
        code, out, err = self.run_cli(["handoff", "--in-flight", "x", "--learned", "y"], "sess-a", self.work)
        self.assertIn("--remote-control alpha-g2 ", out.splitlines()[0])

    def test_handoff_output_for_non_keeper_has_no_remote_control(self):
        self.run_cli(["party", "start", "alpha"], "sess-a", self.work)
        code, out, err = self.run_cli(["handoff", "--in-flight", "x", "--learned", "y"], "sess-a", self.work)
        self.assertNotIn("--remote-control", out)


class KeeperNudgeTests(GuildTestCase):
    def _nudge(self, start_args):
        return self._nudge_with_windows(start_args, [])

    def _nudge_with_windows(self, start_args, window_generations):
        repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(start_args, "sess-1", repo_dir)
        self._record_windows(window_generations)
        config_file = self.config_home / "guild" / "projects" / "acme.json"
        data = json.loads(config_file.read_text())
        data["handoff_threshold"] = 80
        config_file.write_text(json.dumps(data))
        statusline_commands.record_ctx(paths.state_dir(), "sess-1", 85)
        code, out, err = self.run_hook("prompt-submit", {"session_id": "sess-1", "cwd": str(repo_dir)})
        return out

    def _record_windows(self, generations):
        conn = db.connect(paths.db_path())
        with db.writing(conn):
            for generation in generations:
                events.record(
                    conn, timeutil.utcnow(), "tester@host", "alpha", None, "acme", "leader.window_launched", "local",
                    {"party": "alpha", "generation": generation, "window_id": "@{}".format(generation)},
                )
        conn.close()

    def test_keeper_nudge_names_respawn(self):
        out = self._nudge(["party", "start", "alpha", "--keeper"])
        self.assertIn(
            'Context at 85%. Start nothing new; let in-flight runs finish, then run '
            '`guild handoff --respawn --in-flight "..." --learned "..."`. Nothing after it.',
            out,
        )

    def test_normal_nudge_names_plain_handoff(self):
        out = self._nudge(["party", "start", "alpha"])
        self.assertIn(
            'Context at 85%. Start nothing new; let in-flight runs finish, then run '
            '`guild handoff --in-flight "..." --learned "..."`. '
            'Give the human the printed command, then nothing.',
            out,
        )

    def test_normal_nudge_in_guild_window_stays_plain(self):
        out = self._nudge_with_windows(["party", "start", "alpha"], [1])
        self.assertIn(
            'Context at 85%. Start nothing new; let in-flight runs finish, then run '
            '`guild handoff --in-flight "..." --learned "..."`. '
            'Give the human the printed command, then nothing.',
            out,
        )

    def test_normal_nudge_with_window_of_other_generation_stays_plain(self):
        out = self._nudge_with_windows(["party", "start", "alpha"], [2])
        self.assertIn(
            'Context at 85%. Start nothing new; let in-flight runs finish, then run '
            '`guild handoff --in-flight "..." --learned "..."`. '
            'Give the human the printed command, then nothing.',
            out,
        )
