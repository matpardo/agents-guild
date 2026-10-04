import os
import json
import shlex
from unittest import mock

from guild import db, paths, resume
from guild.cli import _build_context
from guild.commands import revive
from guild.errors import GuildError
from tests.testutil import GuildTestCase


class FakeTmux:
    def __init__(self, installed, sessions, windows):
        self._installed = installed
        self.sessions = set(sessions)
        self.windows = list(windows)
        self.calls = []

    def installed(self):
        return self._installed

    def run(self, args):
        self.calls.append(list(args))
        verb = args[0]
        if verb == "has-session":
            return (0 if args[2] in self.sessions else 1), ""
        if verb == "list-windows":
            return 0, "\n".join(self.windows) + "\n"
        if verb == "new-session":
            self.sessions.add(args[args.index("-s") + 1])
            self.windows.append(args[args.index("-n") + 1])
            return 0, "@{}\n".format(len(self.windows))
        if verb == "new-window":
            self.windows.append(args[args.index("-n") + 1])
            return 0, "@{}\n".format(len(self.windows))
        return 0, ""

    def verbs(self):
        return [call[0] for call in self.calls]


def _write_transcript(projects_dir, encoded, session_id, lines):
    directory = projects_dir / encoded
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "{}.jsonl".format(session_id)).write_text(
        "\n".join(json.dumps(line) for line in lines) + "\n"
    )


class ResumeHelperTests(GuildTestCase):
    def test_resume_command_names_party_and_mode(self):
        self.assertEqual(
            resume.resume_command("sess-1", "alpha", 3, "acceptEdits", False),
            "claude --resume sess-1 --name alpha-g3 --permission-mode acceptEdits",
        )

    def test_resume_command_omits_unknown_mode(self):
        self.assertEqual(
            resume.resume_command("sess-1", "alpha", 3, None, False), "claude --resume sess-1 --name alpha-g3"
        )

    def test_fresh_command_keeps_generation_name_and_adds_mode(self):
        command = resume.fresh_command("alpha", 3, None, "plan", False)
        self.assertTrue(
            command.startswith("GUILD_RESUME=alpha claude -n alpha-g3 --permission-mode plan ")
        )

    def test_fresh_command_without_mode_or_model(self):
        command = resume.fresh_command("alpha", 2, None, None, False)
        self.assertNotIn("--permission-mode", command)
        self.assertNotIn("--model", command)

    def test_tab_command_quotes_everything(self):
        line = resume.tab_command("my party", "/tmp/a b", "claude --resume x")
        self.assertEqual(
            line,
            "printf '\\033]0;%s\\007' 'my party' && cd '/tmp/a b' && claude --resume x",
        )


class TranscriptTests(GuildTestCase):
    def test_find_transcript_by_session_id(self):
        _write_transcript(self.claude_projects_dir, "-x", "s1", [{"cwd": "/a"}])
        found = revive.find_transcript(self.claude_projects_dir, "s1")
        self.assertEqual(found.name, "s1.jsonl")

    def test_find_transcript_missing_returns_none(self):
        self.assertIsNone(revive.find_transcript(self.claude_projects_dir, "nope"))

    def test_find_transcript_without_session_id_returns_none(self):
        self.assertIsNone(revive.find_transcript(self.claude_projects_dir, None))

    def test_read_location_stops_after_both_found(self):
        _write_transcript(
            self.claude_projects_dir,
            "-x",
            "s1",
            [{"type": "summary"}, {"cwd": "/a", "permissionMode": "plan"}, {"cwd": "/later"}],
        )
        path = revive.find_transcript(self.claude_projects_dir, "s1")
        self.assertEqual(revive.read_location(path), ("/a", "plan"))

    def test_read_location_collects_across_lines(self):
        _write_transcript(
            self.claude_projects_dir, "-x", "s1", [{"cwd": "/a"}, {"permissionMode": "default"}]
        )
        path = revive.find_transcript(self.claude_projects_dir, "s1")
        self.assertEqual(revive.read_location(path), ("/a", "default"))

    def test_read_location_ignores_garbage_lines(self):
        directory = self.claude_projects_dir / "-x"
        directory.mkdir()
        path = directory / "s1.jsonl"
        path.write_text("not json\n" + json.dumps({"cwd": "/a"}) + "\n")
        self.assertEqual(revive.read_location(path), ("/a", None))

    def test_read_location_gives_up_after_line_limit(self):
        directory = self.claude_projects_dir / "-x"
        directory.mkdir()
        path = directory / "s1.jsonl"
        filler = json.dumps({"type": "noise"}) + "\n"
        path.write_text(filler * revive.TRANSCRIPT_LINE_LIMIT + json.dumps({"cwd": "/late"}) + "\n")
        self.assertEqual(revive.read_location(path), (None, None))


class ReviveBase(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.work_a = self.repo_dir.parent / "work-a"
        self.work_a.mkdir()
        self.work_b = self.repo_dir.parent / "work-b"
        self.work_b.mkdir()
        self.run_cli(["party", "start", "alpha"], "sess-a", self.work_a)
        self.run_cli(["party", "start", "beta"], "sess-b", self.work_b)
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-a", self.work_a)
        self.run_cli(["task", "add", "demo/T01", "--title", "First"], "sess-a", self.work_a)
        self.run_cli(["task", "add", "demo/T02", "--title", "Second"], "sess-a", self.work_a)
        self.conn = db.connect(paths.db_path())

    def _set_leader(self, party, cwd, mode):
        with db.writing(self.conn):
            self.conn.execute(
                "UPDATE leaders SET cwd = ?, permission_mode = ? WHERE party = ?", (cwd, mode, party)
            )

    def _revive(self, party_names, select_all, list_only, tmux, ask_numbers):
        return revive.run(
            _build_context(None, self.root),
            party_names,
            select_all,
            list_only,
            self.claude_projects_dir,
            tmux,
            ask_numbers,
        )

    def _tmux(self, installed=True, sessions=(), windows=()):
        return FakeTmux(installed, sessions, windows)


class ListTests(ReviveBase):
    def test_list_shows_parties_with_location_and_resume_state(self):
        self._set_leader("alpha", str(self.work_a), "acceptEdits")
        _write_transcript(self.claude_projects_dir, "-a", "sess-a", [{"cwd": str(self.work_a)}])
        tmux = self._tmux(installed=False)
        out = self._revive([], False, True, tmux, None)
        self.assertIn("1. alpha", out)
        self.assertIn("2. beta", out)
        self.assertIn("demo 0/2", out)
        self.assertIn("resume", out)
        self.assertIn("fresh", out)
        self.assertIn(str(self.work_a), out)
        self.assertIn("acceptEdits", out)
        self.assertEqual(tmux.calls, [])

    def test_list_shows_status_line_after_quest_line(self):
        self.write_session(os.getpid(), "sess-a", "alpha-g1")
        self.run_hook(
            "notification",
            {
                "session_id": "sess-a",
                "cwd": str(self.work_a),
                "notification_type": "permission_prompt",
                "message": "x",
            },
        )
        out = self._revive([], False, True, self._tmux(installed=False), None)
        lines = out.splitlines()
        alpha_quest = next(i for i, line in enumerate(lines) if line.startswith("   quest: demo 0/2"))
        self.assertRegex(lines[alpha_quest + 1], r"^   status: waiting-permission \d+s$")
        beta_status = next(line for line in lines if line.startswith("   status: ") and "idle" in line)
        self.assertEqual(beta_status, "   status: idle")

    def test_list_prints_copy_paste_one_liner_per_party(self):
        self._set_leader("alpha", str(self.work_a), "acceptEdits")
        _write_transcript(self.claude_projects_dir, "-a", "sess-a", [{"cwd": str(self.work_a)}])
        out = self._revive([], False, True, self._tmux(), None)
        expected = resume.tab_command(
            "alpha",
            str(self.work_a),
            resume.resume_command("sess-a", "alpha", 1, "acceptEdits", False),
        )
        self.assertIn(expected, out)

    def test_list_one_liner_for_fresh_uses_fresh_command(self):
        self._set_leader("beta", str(self.work_b), None)
        out = self._revive([], False, True, self._tmux(), None)
        self.assertIn("GUILD_RESUME=beta claude -n beta-g2", out)

    def test_list_falls_back_to_transcript_for_cwd_and_mode(self):
        self._set_leader("alpha", None, None)
        _write_transcript(
            self.claude_projects_dir,
            "-a",
            "sess-a",
            [{"cwd": str(self.work_a), "permissionMode": "plan"}],
        )
        out = self._revive([], False, True, self._tmux(), None)
        self.assertIn("--permission-mode plan", out)
        self.assertIn(shlex.quote(str(self.work_a)), out)

    def test_leader_columns_win_over_transcript(self):
        self._set_leader("alpha", str(self.work_a), "acceptEdits")
        _write_transcript(
            self.claude_projects_dir,
            "-a",
            "sess-a",
            [{"cwd": "/elsewhere", "permissionMode": "plan"}],
        )
        out = self._revive([], False, True, self._tmux(), None)
        self.assertIn("--permission-mode acceptEdits", out)
        self.assertNotIn("/elsewhere", out)

    def test_unknown_mode_is_never_invented(self):
        self._set_leader("beta", str(self.work_b), None)
        out = self._revive(["beta"], False, True, self._tmux(), None)
        self.assertNotIn("--permission-mode", out)

    def test_closed_party_not_listed(self):
        self.run_cli(["party", "close", "beta"], "sess-b", self.work_b)
        out = self._revive([], False, True, self._tmux(), None)
        self.assertNotIn("beta", out)

    def test_no_active_parties(self):
        self.run_cli(["party", "close", "alpha", "--force"], "sess-a", self.work_a)
        self.run_cli(["party", "close", "beta"], "sess-b", self.work_b)
        out = self._revive([], False, True, self._tmux(), None)
        self.assertEqual(out, "no active parties")


class SelectionTests(ReviveBase):
    def setUp(self):
        super().setUp()
        self._set_leader("alpha", str(self.work_a), "acceptEdits")
        self._set_leader("beta", str(self.work_b), None)
        _write_transcript(self.claude_projects_dir, "-a", "sess-a", [{"cwd": str(self.work_a)}])

    def test_no_selection_and_no_tty_lists_with_hint(self):
        tmux = self._tmux()
        out = self._revive([], False, False, tmux, None)
        self.assertIn("1. alpha", out)
        self.assertIn("--party", out)
        self.assertIn("--all", out)
        self.assertEqual(tmux.calls, [])

    def test_interactive_numbers_select_parties(self):
        tmux = self._tmux()
        prompts = []

        def ask(prompt):
            prompts.append(prompt)
            return "2"

        out = self._revive([], False, False, tmux, ask)
        self.assertEqual(len(prompts), 1)
        self.assertIn("1. alpha", prompts[0])
        self.assertTrue(prompts[0].endswith("numbers to revive (e.g. 1,3): "))
        self.assertEqual(tmux.windows, ["beta"])
        self.assertIn("launched beta", out)

    def test_interactive_invalid_number_errors(self):
        with self.assertRaises(GuildError):
            self._revive([], False, False, self._tmux(), lambda prompt: "9")

    def test_interactive_non_number_errors(self):
        with self.assertRaises(GuildError):
            self._revive([], False, False, self._tmux(), lambda prompt: "x")

    def test_interactive_blank_launches_nothing(self):
        tmux = self._tmux()
        out = self._revive([], False, False, tmux, lambda prompt: "  ")
        self.assertEqual(tmux.windows, [])
        self.assertIn("nothing selected", out)

    def test_unknown_party_errors(self):
        with self.assertRaises(GuildError) as raised:
            self._revive(["ghost"], False, False, self._tmux(), None)
        self.assertIn("ghost", raised.exception.message)

    def test_all_launches_every_party(self):
        tmux = self._tmux()
        self._revive([], True, False, tmux, None)
        self.assertEqual(sorted(tmux.windows), ["alpha", "beta"])


class LaunchTests(ReviveBase):
    def setUp(self):
        super().setUp()
        self._set_leader("alpha", str(self.work_a), "acceptEdits")
        self._set_leader("beta", str(self.work_b), None)
        _write_transcript(self.claude_projects_dir, "-a", "sess-a", [{"cwd": str(self.work_a)}])

    def test_creates_session_with_resume_command_and_name_options(self):
        tmux = self._tmux()
        out = self._revive(["alpha"], False, False, tmux, None)
        self.assertIn(
            [
                "new-session", "-d", "-s", "guild", "-n", "alpha", "-c", str(self.work_a),
                "-P", "-F", "#{window_id}",
                "claude --resume sess-a --name alpha-g1 --permission-mode acceptEdits",
            ],
            tmux.calls,
        )
        self.assertIn(["set-option", "-w", "-t", "@1", "automatic-rename", "off"], tmux.calls)
        self.assertIn(["set-option", "-w", "-t", "@1", "allow-rename", "off"], tmux.calls)
        self.assertIn(["set-option", "-t", "guild", "set-titles", "on"], tmux.calls)
        self.assertIn(["set-option", "-t", "guild", "set-titles-string", "#W"], tmux.calls)
        self.assertIn("launched alpha (resume)", out)

    def test_never_touches_global_options(self):
        tmux = self._tmux()
        self._revive([], True, False, tmux, None)
        for call in tmux.calls:
            self.assertNotIn("-g", call)

    def test_existing_session_uses_new_window(self):
        tmux = self._tmux(sessions=["guild"], windows=["other"])
        self._revive(["alpha"], False, False, tmux, None)
        self.assertNotIn("new-session", tmux.verbs())
        new_window = [call for call in tmux.calls if call[0] == "new-window"][0]
        self.assertEqual(new_window[:6], ["new-window", "-t", "guild:", "-n", "alpha", "-c"])

    def test_existing_window_for_party_is_skipped(self):
        tmux = self._tmux(sessions=["guild"], windows=["alpha"])
        out = self._revive(["alpha"], False, False, tmux, None)
        self.assertNotIn("new-window", tmux.verbs())
        self.assertIn("skipped alpha: window already exists", out)

    def test_fresh_fallback_without_transcript(self):
        tmux = self._tmux()
        out = self._revive(["beta"], False, False, tmux, None)
        new_session = [call for call in tmux.calls if call[0] == "new-session"][0]
        self.assertTrue(new_session[-1].startswith("GUILD_RESUME=beta claude -n beta-g2 "))
        self.assertIn("launched beta (fresh)", out)

    def test_missing_cwd_is_skipped_with_reason(self):
        self._set_leader("alpha", str(self.root / "gone"), "acceptEdits")
        tmux = self._tmux()
        out = self._revive(["alpha"], False, False, tmux, None)
        self.assertEqual(tmux.windows, [])
        self.assertIn("skipped alpha: cwd missing", out)
        self.assertIn(str(self.root / "gone"), out)
        self.assertIn("fresh session", out)

    def test_unknown_cwd_is_skipped_with_reason(self):
        self._set_leader("beta", None, None)
        tmux = self._tmux()
        out = self._revive(["beta"], False, False, tmux, None)
        self.assertIn("skipped beta: cwd unknown", out)

    def test_tmux_absent_is_an_error_with_install_hint(self):
        with self.assertRaises(GuildError) as raised:
            self._revive(["alpha"], False, False, self._tmux(installed=False), None)
        self.assertIn("install tmux", raised.exception.message)

    def test_output_ends_with_attach_line_and_goal_reminder(self):
        out = self._revive(["alpha"], False, False, self._tmux(), None)
        lines = out.splitlines()
        self.assertEqual(lines[-1], "tmux attach -t guild")
        self.assertIn("/goal", lines[-2])

    def test_failed_tmux_launch_is_reported(self):
        tmux = self._tmux()
        original = tmux.run

        def failing(args):
            if args[0] == "new-session":
                return 1, ""
            return original(args)

        tmux.run = failing
        out = self._revive(["alpha"], False, False, tmux, None)
        self.assertIn("failed alpha", out)


class CliWiringTests(ReviveBase):
    def test_cli_list_works_without_tmux(self):
        self._set_leader("alpha", str(self.work_a), "acceptEdits")
        with mock.patch("shutil.which", return_value=None):
            code, out, err = self.run_cli(["revive", "--list"], None, self.root)
        self.assertEqual(code, 0, err)
        self.assertIn("1. alpha", out)

    def test_cli_launch_without_tmux_fails_with_hint(self):
        with mock.patch("shutil.which", return_value=None):
            code, out, err = self.run_cli(["revive", "--party", "alpha"], None, self.root)
        self.assertEqual(code, 1)
        self.assertIn("install tmux", err)
