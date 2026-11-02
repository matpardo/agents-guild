import json
import os
import sqlite3
from datetime import timedelta
from unittest import mock

from guild import config, paths, reducers, solo_players, timeutil
from guild.errors import GuildError
from tests.test_revive import FakeTmux
from tests.testutil import GuildTestCase

_BASE = {"name": "acme", "paths": ["/tmp/acme/*"], "github": {"repos": ["acme/app", "other/app"]}}
_RED = {"repo": "acme/app", "job": "red-main", "name": "mender"}
_DEP = {"repo": "acme/app", "job": "dependabot"}
_GREEN_PR = {"number": 1, "mergeable": "MERGEABLE", "mergeStateStatus": "CLEAN", "statusCheckRollup": []}


def _with_players(players):
    return dict(_BASE, solo_players=players)


class SoloPlayersConfigTests(GuildTestCase):
    def test_absent_key_and_valid_players_load(self):
        config.validate_project_config(_BASE)
        config.validate_project_config(_with_players([_RED, _DEP, dict(_RED, repo="other/app")]))

    def test_invalid_shapes_fail_naming_the_key(self):
        bad = [
            "x",
            {},
            ["x"],
            [{"repo": "acme/app"}],
            [{"job": "red-main"}],
            [dict(_RED, extra=1)],
            [dict(_RED, job="nope")],
            [dict(_RED, job=3)],
            [dict(_RED, repo="nobody/else")],
            [dict(_RED, name="")],
            [dict(_RED, name="  ")],
            [dict(_RED, name=3)],
            [_RED, dict(_RED, name="other")],
        ]
        for players in bad:
            with self.assertRaises(GuildError, msg=players) as raised:
                config.validate_project_config(_with_players(players))
            self.assertIn("solo_players", raised.exception.message)


class KillingTmux(FakeTmux):
    def __init__(self, installed, sessions, windows, kill_returncode):
        super().__init__(installed, sessions, windows)
        self.kill_returncode = kill_returncode
        self.killed = []

    def run(self, args):
        if args[0] != "kill-window":
            return super().run(args)
        self.calls.append(list(args))
        if self.kill_returncode == 0:
            self.killed.append(args[2])
            self.windows = [name for name in self.windows if args[2] != "guild:=" + name]
        return self.kill_returncode, ""


class SoloPlayersTestCase(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.project_dir = self.repo_dir.parent
        self.set_players([_RED, _DEP])
        self.cli(["whoami"], None)

    def set_players(self, players):
        path = self.config_home / "guild" / "projects" / "acme.json"
        data = json.loads(path.read_text())
        data["solo_players"] = players
        path.write_text(json.dumps(data))

    def cli(self, argv, session_id):
        return self.run_cli(argv, session_id, self.repo_dir)

    def db(self):
        conn = sqlite3.connect(str(paths.db_path()))
        conn.row_factory = sqlite3.Row
        self.addCleanup(conn.close)
        return conn

    def players(self):
        from guild.cli import _build_context
        from guild.commands import board

        board_model = board.board_model(_build_context(None, self.repo_dir))
        return {(row["repo"], row["job"]): row for row in board_model["solo_players"]}

    def red(self, reason):
        return self.cli(["main", "red", "acme/app", "--reason", reason], None)

    def finish_job(self, health_job, pending):
        self.cli(["adventurer", "start", "--job", health_job, "--reason", "test reason"], "adv-1")
        self.cli(["adventurer", "done", "--pending", pending], "adv-1")

    def launch_manually(self):
        with mock.patch("guild.tmux_windows.Tmux", return_value=FakeTmux(True, [], [])):
            self.assertEqual(self.cli(["solo", "launch", "acme/app", "red-main"], None)[0], 0)

    def channel_texts(self):
        return [row["text"] for row in self.db().execute("SELECT text FROM solo_messages ORDER BY id").fetchall()]

    def start_player(self, health_job, session_id):
        self.cli(["adventurer", "start", "--job", health_job, "--reason", "test reason"], session_id)

    def age_reports(self, hours):
        old = timeutil.to_iso(timeutil.utcnow() - timedelta(hours=hours))
        conn = self.db()
        conn.execute("UPDATE adventurers SET done_at = ?", (old,))
        conn.commit()


class SoloPlayersJobsTests(SoloPlayersTestCase):
    def test_jobs_derive_a_health_job_per_player(self):
        data = config.load_project(self.config_home / "guild" / "projects", "acme")
        derived = {job["name"]: job for job in solo_players.jobs(data)}
        self.assertEqual(set(derived), {"red-main-acme-app", "dependabot-acme-app"})
        self.assertEqual(derived["red-main-acme-app"]["every"], "1h")
        self.assertIn("Main of acme/app is red", derived["red-main-acme-app"]["command"])
        self.assertIn("dependabot[bot]", derived["dependabot-acme-app"]["command"])

    def test_same_repo_name_under_two_owners_does_not_collide(self):
        names = {solo_players.health_job_name(repo, "red-main") for repo in ("a/app", "b/app")}
        self.assertEqual(len(names), 2)

    def test_start_by_derived_job_name_binds_the_adventurer(self):
        code, out, err = self.cli(
            ["adventurer", "start", "--job", "red-main-acme-app", "--reason", "test reason"], "adv-1"
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(self.db().execute("SELECT health_job FROM adventurers").fetchone()[0], "red-main-acme-app")

    def test_hook_applies_a_derived_job(self):
        with mock.patch.dict(os.environ, {"GUILD_ADVENTURER_JOB": "dependabot-acme-app"}):
            code, out, err = self.run_hook(
                "session-start", {"session_id": "adv-1", "cwd": str(self.repo_dir), "source": "startup"}
            )
        self.assertIn("adventurer 1 started", out)

    def test_health_jobs_section_lists_only_configured_jobs(self):
        code, out, err = self.cli(["board"], None)
        self.assertNotIn("HEALTH JOBS", out)


class SoloPlayersTriggerTests(SoloPlayersTestCase):
    def test_without_triggers_every_player_is_idle(self):
        rows = self.players()
        self.assertEqual({row["state"] for row in rows.values()}, {"idle"})
        self.assertEqual(rows[("acme/app", "red-main")]["class"], "cleric")
        self.assertEqual(rows[("acme/app", "dependabot")]["class"], "artificer")
        self.assertEqual(rows[("acme/app", "red-main")]["name"], "mender")
        self.assertEqual(rows[("acme/app", "dependabot")]["name"], "dependabot")

    def test_manual_red_main_is_due(self):
        self.red("ci down")
        row = self.players()[("acme/app", "red-main")]
        self.assertEqual(row["state"], "due")
        self.assertEqual(row["trigger"], "main red: ci down")
        self.assertEqual(row["launch"], "guild solo launch acme/app red-main")

    def test_gh_red_main_is_due(self):
        conn = self.db()
        conn.execute(
            "INSERT INTO main_status (repo, source, red, reason, external, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("acme/app", "gh", 1, "checks failing: lint", None, "2026-11-01T00:00:00+00:00"),
        )
        conn.commit()
        self.assertEqual(self.players()[("acme/app", "red-main")]["state"], "due")

    def test_billing_red_main_never_triggers(self):
        conn = self.db()
        conn.execute(
            "INSERT INTO main_status (repo, source, red, reason, external, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("acme/app", "gh", 1, "checks failing: lint", "billing", "2026-11-01T00:00:00+00:00"),
        )
        conn.commit()
        self.assertEqual(self.players()[("acme/app", "red-main")]["state"], "idle")

    def test_green_main_clears_the_trigger(self):
        self.red("ci down")
        self.cli(["main", "green", "acme/app"], None)
        self.assertEqual(self.players()[("acme/app", "red-main")]["state"], "idle")

    def test_active_adventurer_means_running(self):
        self.red("ci down")
        self.cli(["adventurer", "start", "--job", "red-main-acme-app", "--reason", "test reason"], "adv-1")
        self.write_session(os.getpid(), "adv-1", "adv")
        self.assertEqual(self.players()[("acme/app", "red-main")]["state"], "running")

    def test_report_within_cooldown_means_cooling_and_keeps_last_pending(self):
        self.red("ci down")
        self.finish_job("red-main-acme-app", "waiting on review")
        row = self.players()[("acme/app", "red-main")]
        self.assertEqual(row["state"], "cooling")
        self.assertEqual(row["last_pending"], "waiting on review")
        self.assertIsNotNone(row["last_done"])

    def test_report_older_than_cooldown_is_due_again(self):
        self.red("ci down")
        self.finish_job("red-main-acme-app", "none")
        self.age_reports(2)
        self.assertEqual(self.players()[("acme/app", "red-main")]["state"], "due")

    def test_dependabot_trigger_reads_unmergeable_or_failed_run(self):
        conn = self.db()
        conn.execute("INSERT INTO dependabot_status VALUES ('acme/app', 0, 0, 'x')")
        conn.commit()
        self.assertEqual(self.players()[("acme/app", "dependabot")]["state"], "idle")
        conn.execute("UPDATE dependabot_status SET unmergeable = 2, run_failed = 1")
        conn.commit()
        row = self.players()[("acme/app", "dependabot")]
        self.assertEqual(row["state"], "due")
        self.assertEqual(row["trigger"], "2 unmergeable dependabot PRs, dependabot update run failing")


class SoloPlayersStalledTests(SoloPlayersTestCase):
    def start_job(self):
        self.red("ci down")
        self.cli(["adventurer", "start", "--job", "red-main-acme-app", "--reason", "test reason"], "adv-1")

    def red_row(self):
        return self.players()[("acme/app", "red-main")]

    def test_active_adventurer_with_live_session_is_running(self):
        self.start_job()
        self.write_session(os.getpid(), "adv-1", "adv")
        row = self.red_row()
        self.assertEqual(row["state"], "running")
        self.assertIsNone(row["stalled_adventurer"])

    def test_active_adventurer_with_dead_session_is_stalled_with_its_id(self):
        self.start_job()
        row = self.red_row()
        self.assertEqual(row["state"], "stalled")
        self.assertEqual(row["stalled_adventurer"], 1)

    def test_dismissed_adventurer_is_not_stalled_and_player_is_due_again(self):
        self.start_job()
        code, out, err = self.cli(["adventurer", "dismiss", "1"], None)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.red_row()["state"], "due")

    def test_dismiss_refuses_an_active_adventurer_with_a_live_session(self):
        self.start_job()
        self.write_session(os.getpid(), "adv-1", "adv")
        code, out, err = self.cli(["adventurer", "dismiss", "1"], None)
        self.assertNotEqual(code, 0)
        self.assertEqual(self.red_row()["state"], "running")

    def test_text_board_and_list_show_the_dismiss_hint_without_launch_command(self):
        self.start_job()
        out = self.cli(["board"], None)[1]
        self.assertIn("acme/app stalled: session gone, run guild adventurer dismiss 1 main red: ci down", out)
        self.assertNotIn("guild solo launch acme/app red-main", out)
        self.assertIn(
            "acme/app red-main stalled: session gone, run guild adventurer dismiss 1",
            self.cli(["solo", "list"], None)[1],
        )

    def test_tick_does_not_launch_a_stalled_player(self):
        self.start_job()
        tmux = FakeTmux(True, [], [])
        with mock.patch("guild.tmux_windows.Tmux", return_value=tmux):
            code, out, err = self.cli(["solo", "tick"], None)
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "")
        self.assertEqual(tmux.windows, [])


class SoloPlayersFixingTests(SoloPlayersTestCase):
    def add_pr(self, repo, number, lifecycle, fixes_main):
        conn = self.db()
        conn.execute(
            "INSERT INTO prs (repo, number, party, what, lifecycle, seeded, fixes_main)"
            " VALUES (?, ?, 'p', 'fix', ?, 0, ?)",
            (repo, number, lifecycle, fixes_main),
        )
        conn.commit()

    def red_state(self):
        return self.players()[("acme/app", "red-main")]

    def test_open_fixes_main_pr_holds_the_player_with_its_ref(self):
        self.red("ci down")
        self.add_pr("acme/app", 12, "ready", 1)
        row = self.red_state()
        self.assertEqual(row["state"], "fixing")
        self.assertEqual(row["waits_on"], ["acme/app#12"])

    def test_merged_or_closed_fixes_main_pr_does_not_hold(self):
        self.red("ci down")
        self.add_pr("acme/app", 12, "merged", 1)
        self.add_pr("acme/app", 13, "closed", 1)
        self.assertEqual(self.red_state()["state"], "due")
        self.assertEqual(self.red_state()["waits_on"], [])

    def test_open_pr_without_fixes_main_does_not_hold(self):
        self.red("ci down")
        self.add_pr("acme/app", 12, "ready", 0)
        self.assertEqual(self.red_state()["state"], "due")

    def test_other_repo_pr_does_not_hold(self):
        self.red("ci down")
        self.add_pr("other/app", 12, "ready", 1)
        self.assertEqual(self.red_state()["state"], "due")

    def test_dependabot_player_is_never_fixing(self):
        self.add_pr("acme/app", 12, "ready", 1)
        self.assertEqual(self.players()[("acme/app", "dependabot")]["state"], "idle")

    def test_text_board_and_list_show_what_it_waits_on(self):
        self.red("ci down")
        self.add_pr("acme/app", 12, "ready", 1)
        out = self.cli(["board"], None)[1]
        self.assertIn("mender [cleric] acme/app fixing: waits on acme/app#12 main red: ci down", out)
        self.assertNotIn("guild solo launch acme/app red-main", out)
        self.assertIn("acme/app red-main fixing", self.cli(["solo", "list"], None)[1])

    def test_tick_does_not_launch_a_fixing_player(self):
        self.red("ci down")
        self.add_pr("acme/app", 12, "ready", 1)
        tmux = FakeTmux(True, [], [])
        with mock.patch("guild.tmux_windows.Tmux", return_value=tmux):
            code, out, err = self.cli(["solo", "tick"], None)
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "")
        self.assertEqual(tmux.windows, [])


class SoloPlayersBoardTests(SoloPlayersTestCase):
    def test_text_board_lists_players_with_launch_command(self):
        self.red("ci down")
        code, out, err = self.cli(["board"], None)
        self.assertEqual(code, 0, err)
        self.assertIn("SOLO PLAYERS", out)
        self.assertIn("mender [cleric] acme/app due main red: ci down", out)
        self.assertIn("guild solo launch acme/app red-main", out)
        self.assertIn("guild solo launch acme/app dependabot", out)

    def test_text_board_says_no_trigger_for_an_idle_player(self):
        code, out, err = self.cli(["board"], None)
        self.assertEqual(code, 0, err)
        self.assertIn("mender [cleric] acme/app idle no trigger", out)
        self.assertNotIn("idle idle", out)

    def test_text_board_without_players_has_no_section(self):
        self.set_players([])
        code, out, err = self.cli(["board"], None)
        self.assertNotIn("SOLO PLAYERS", out)

    def test_solo_list_prints_the_rows(self):
        code, out, err = self.cli(["solo", "list"], None)
        self.assertEqual(code, 0, err)
        self.assertIn("mender [cleric] acme/app red-main idle", out)
        self.assertIn("dependabot [artificer] acme/app dependabot idle", out)
        self.assertEqual(out.splitlines()[0], "acme")

    def test_solo_list_project_filter(self):
        code, out, err = self.cli(["solo", "list", "--project", "acme"], None)
        self.assertEqual(code, 0, err)
        self.assertEqual(out.splitlines()[0], "acme")
        self.assertEqual(self.cli(["solo", "list", "--project", "nope"], None)[0], 1)

    def test_text_board_groups_players_under_a_project_header(self):
        lines = self.cli(["board"], None)[1].splitlines()
        start = next(index for index, line in enumerate(lines) if "SOLO PLAYERS" in line)
        self.assertEqual(lines[start + 1].strip(), "acme")

    def test_solo_list_without_players(self):
        self.set_players([])
        self.assertEqual(self.cli(["solo", "list"], None)[1].strip(), "no solo players")


class SoloPlayersStatusTests(SoloPlayersTestCase):
    def test_status_without_args_lists_every_player_grouped(self):
        code, out, err = self.cli(["solo", "status"], None)
        self.assertEqual(code, 0, err)
        self.assertEqual(out.splitlines()[0], "acme")
        self.assertIn("mender [cleric] acme/app red-main idle", out)
        self.assertIn("dependabot [artificer] acme/app dependabot idle", out)

    def test_status_matches_list(self):
        self.assertEqual(self.cli(["solo", "status"], None)[1], self.cli(["solo", "list"], None)[1])

    def test_status_project_scope(self):
        code, out, err = self.cli(["solo", "status", "--project", "acme"], None)
        self.assertEqual(code, 0, err)
        self.assertEqual(out.splitlines()[0], "acme")

    def test_status_unknown_project_fails(self):
        code, out, err = self.cli(["solo", "status", "--project", "nope"], None)
        self.assertEqual(code, 1)
        self.assertIn("unknown project", err)

    def test_status_single_player_adds_runs_and_channel(self):
        for number in range(7):
            self.finish_job("red-main-acme-app", "run {}".format(number))
        self.launch_manually()
        code, out, err = self.cli(["solo", "status", "acme/app", "red-main"], None)
        self.assertEqual(code, 0, err)
        self.assertEqual(out.splitlines()[0], "acme")
        self.assertIn("mender [cleric] acme/app red-main", out)
        self.assertIn("runs", out)
        self.assertIn("run 6", out)
        self.assertEqual(out.count(" done 0s "), 5)
        self.assertIn("channel", out)
        self.assertIn("mender (cleric) started on acme/app: manual launch", out)

    def test_status_single_player_channel_keeps_only_its_messages_and_ten(self):
        self.launch_manually()
        with mock.patch("guild.tmux_windows.Tmux", return_value=FakeTmux(True, [], [])):
            self.cli(["solo", "launch", "acme/app", "dependabot"], None)
        out = self.cli(["solo", "status", "acme/app", "red-main"], None)[1]
        self.assertIn("mender (cleric) started", out)
        self.assertNotIn("dependabot (artificer) started", out)

    def test_status_single_player_without_runs_or_messages(self):
        out = self.cli(["solo", "status", "acme/app", "red-main"], None)[1]
        self.assertIn("no runs", out)
        self.assertIn("no messages", out)

    def test_status_unknown_player_fails(self):
        code, out, err = self.cli(["solo", "status", "acme/app", "nope"], None)
        self.assertEqual(code, 1)
        self.assertIn("no solo player", err)

    def test_status_rejects_mixed_scopes(self):
        self.assertEqual(self.cli(["solo", "status", "acme/app", "red-main", "--project", "acme"], None)[0], 1)
        self.assertEqual(self.cli(["solo", "status", "acme/app"], None)[0], 1)


class SoloPlayersLaunchTests(SoloPlayersTestCase):
    def launch(self, argv, session_id, tmux):
        with mock.patch("guild.tmux_windows.Tmux", return_value=tmux):
            return self.cli(argv, session_id)

    def test_launch_opens_a_solo_window_even_when_not_due(self):
        tmux = FakeTmux(True, [], [])
        code, out, err = self.launch(["solo", "launch", "acme/app", "red-main"], None, tmux)
        self.assertEqual(code, 0, err)
        call = next(c for c in tmux.calls if c[0] == "new-session")
        self.assertEqual(call[call.index("-n") + 1], "solo-red-main-acme-app")
        self.assertEqual(call[call.index("-c") + 1], str(self.project_dir))
        self.assertTrue(call[-1].startswith("GUILD_ADVENTURER_JOB=red-main-acme-app claude "))

    def test_launch_finds_the_player_from_a_cwd_outside_any_project(self):
        outside = self.project_dir.parent / "elsewhere"
        outside.mkdir()
        tmux = FakeTmux(True, [], [])
        with mock.patch("guild.tmux_windows.Tmux", return_value=tmux):
            code, out, err = self.run_cli(["solo", "launch", "acme/app", "red-main"], None, outside)
        self.assertEqual(code, 0, err)
        self.assertIn("new-session", tmux.verbs())

    def test_launch_unknown_player_says_no_solo_player(self):
        code, out, err = self.launch(["solo", "launch", "other/app", "red-main"], None, FakeTmux(True, [], []))
        self.assertEqual(code, 1)
        self.assertIn("no solo player 'red-main' on 'other/app'", err)

    def test_launch_refuses_inside_a_session(self):
        tmux = FakeTmux(True, [], [])
        code, out, err = self.launch(["solo", "launch", "acme/app", "red-main"], "sess-1", tmux)
        self.assertEqual(code, 1)
        self.assertEqual(tmux.calls, [])

    def test_launch_refuses_unknown_player_and_existing_window(self):
        self.assertEqual(self.launch(["solo", "launch", "other/app", "red-main"], None, FakeTmux(True, [], []))[0], 1)
        tmux = FakeTmux(True, ["guild"], ["solo-red-main-acme-app"])
        self.assertEqual(self.launch(["solo", "launch", "acme/app", "red-main"], None, tmux)[0], 1)
        self.assertNotIn("new-window", tmux.verbs())


class SoloPlayersPauseTests(SoloPlayersTestCase):
    WINDOW = "solo-red-main-acme-app"

    def run_solo(self, argv, tmux, session_id=None):
        with mock.patch("guild.tmux_windows.Tmux", return_value=tmux):
            return self.cli(["solo"] + argv, session_id)

    def state(self, job="red-main"):
        return self.players()[("acme/app", job)]["state"]

    def adventurer_states(self):
        return [row["state"] for row in self.db().execute("SELECT state FROM adventurers ORDER BY id").fetchall()]

    def test_stop_running_player_kills_window_dismisses_adventurer_and_pauses(self):
        self.start_player("red-main-acme-app", "adv-1")
        tmux = KillingTmux(True, ["guild"], [self.WINDOW], 0)
        with mock.patch("guild.session_info.live_session_ids", return_value={"adv-1"}):
            code, out, err = self.run_solo(["stop", "acme/app", "red-main"], tmux)
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "mender stopped")
        self.assertEqual(tmux.killed, ["guild:=" + self.WINDOW])
        self.assertEqual(self.adventurer_states(), ["dismissed"])
        self.assertEqual(self.state(), "paused")
        self.assertIn("mender stopped by the human", self.channel_texts())

    def test_stop_stalled_player_dismisses_adventurer_and_pauses(self):
        self.start_player("red-main-acme-app", "adv-1")
        tmux = KillingTmux(True, [], [], 1)
        code, out, err = self.run_solo(["stop", "acme/app", "red-main"], tmux)
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "mender stopped")
        self.assertEqual(self.adventurer_states(), ["dismissed"])
        self.assertEqual(self.state(), "paused")

    def test_stop_idle_player_only_pauses(self):
        tmux = KillingTmux(True, ["guild"], [self.WINDOW], 0)
        code, out, err = self.run_solo(["stop", "acme/app", "red-main"], tmux)
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "mender paused")
        self.assertEqual(tmux.killed, [])
        self.assertEqual(self.state(), "paused")
        self.assertIn("mender paused", self.channel_texts())

    def test_stop_without_scope_is_refused(self):
        code, out, err = self.run_solo(["stop"], FakeTmux(True, [], []))
        self.assertEqual(code, 1)
        self.assertEqual(self.state(), "idle")

    def test_stop_rejects_mixed_scopes_and_unknown_targets(self):
        tmux = FakeTmux(True, [], [])
        self.assertEqual(self.run_solo(["stop", "--all", "--project", "acme"], tmux)[0], 1)
        self.assertEqual(self.run_solo(["stop", "--project", "nope"], tmux)[0], 1)
        self.assertEqual(self.run_solo(["stop", "acme/app", "nope"], tmux)[0], 1)
        self.assertEqual(self.state(), "idle")

    def test_stop_already_paused_player(self):
        self.run_solo(["stop", "acme/app", "red-main"], FakeTmux(True, [], []))
        out = self.run_solo(["stop", "acme/app", "red-main"], FakeTmux(True, [], []))[1]
        self.assertEqual(out.strip(), "mender already paused")

    def test_stop_all_and_project_print_one_line_per_player(self):
        for argv in (["stop", "--all"], ["stop", "--project", "acme"]):
            self.cli(["solo", "resume", "--all"], None)
            out = self.run_solo(argv, FakeTmux(True, [], []))[1]
            self.assertEqual(sorted(out.splitlines()), ["dependabot paused", "mender paused"])

    def test_stop_continues_after_a_player_error(self):
        self.start_player("red-main-acme-app", "adv-1")
        tmux = KillingTmux(True, ["guild"], [self.WINDOW], 0)
        with (
            mock.patch("guild.session_info.live_session_ids", return_value={"adv-1"}),
            mock.patch("guild.commands.adventurer.dismiss_stopped", side_effect=GuildError("boom", 1)),
        ):
            out = self.run_solo(["stop", "--all"], tmux)[1]
        self.assertIn("mender not stopped: boom", out)
        self.assertIn("dependabot paused", out)

    def test_resume_unpauses_and_posts(self):
        self.run_solo(["stop", "acme/app", "red-main"], FakeTmux(True, [], []))
        code, out, err = self.cli(["solo", "resume", "acme/app", "red-main"], None)
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "mender resumed")
        self.assertEqual(self.state(), "idle")
        self.assertIn("mender resumed", self.channel_texts())

    def test_resume_not_paused(self):
        out = self.cli(["solo", "resume", "acme/app", "red-main"], None)[1]
        self.assertEqual(out.strip(), "mender not paused")

    def test_resume_requires_a_scope_and_accepts_all_and_project(self):
        self.assertEqual(self.cli(["solo", "resume"], None)[0], 1)
        self.run_solo(["stop", "--all"], FakeTmux(True, [], []))
        out = self.cli(["solo", "resume", "--project", "acme"], None)[1]
        self.assertEqual(sorted(out.splitlines()), ["dependabot resumed", "mender resumed"])
        self.assertEqual(self.cli(["solo", "resume", "--all"], None)[1].count("not paused"), 2)

    def test_stop_and_resume_refuse_inside_a_session(self):
        tmux = FakeTmux(True, [], [])
        self.assertEqual(self.run_solo(["stop", "--all"], tmux, "sess-1")[0], 1)
        self.assertEqual(self.cli(["solo", "resume", "--all"], "sess-1")[0], 1)
        self.assertEqual(self.state(), "idle")

    def test_a_paused_player_is_never_due_and_tick_skips_it(self):
        self.red("ci down")
        self.assertEqual(self.state(), "due")
        self.run_solo(["stop", "acme/app", "red-main"], FakeTmux(True, [], []))
        self.assertEqual(self.state(), "paused")
        tmux = FakeTmux(True, [], [])
        self.run_solo(["tick"], tmux)
        self.assertNotIn("new-session", tmux.verbs())

    def test_launch_skips_a_paused_player(self):
        self.run_solo(["stop", "--all"], FakeTmux(True, [], []))
        tmux = FakeTmux(True, [], [])
        code, out, err = self.run_solo(["launch", "acme/app", "red-main"], tmux)
        self.assertEqual(code, 1)
        self.assertIn("mender skipped: paused, run guild solo resume acme/app red-main", err)
        for argv in (["launch", "--all"], ["launch", "--project", "acme"]):
            out = self.run_solo(argv, tmux)[1]
            self.assertIn("mender skipped: paused, run guild solo resume acme/app red-main", out)
        self.assertEqual(tmux.verbs(), [])

    def test_paused_row_carries_the_resume_command(self):
        self.run_solo(["stop", "acme/app", "red-main"], FakeTmux(True, [], []))
        self.assertEqual(self.players()[("acme/app", "red-main")]["launch"], "guild solo resume acme/app red-main")
        self.assertIn("guild solo resume acme/app red-main", self.cli(["board"], None)[1])

    def test_rebuild_keeps_pauses_and_resumes(self):
        self.run_solo(["stop", "--all"], FakeTmux(True, [], []))
        self.cli(["solo", "resume", "acme/app", "dependabot"], None)
        self.assertEqual(self.cli(["rebuild"], None)[0], 0)
        self.assertEqual(self.state(), "paused")
        self.assertEqual(self.state("dependabot"), "idle")
        rows = self.db().execute("SELECT health_job FROM solo_pauses").fetchall()
        self.assertEqual([row["health_job"] for row in rows], ["red-main-acme-app"])

    def test_payloads_require_repo_and_job(self):
        self.assertEqual(reducers.required_keys("solo.paused"), ("repo", "job"))
        self.assertEqual(reducers.required_keys("solo.resumed"), ("repo", "job"))


class SoloPlayersTickTests(SoloPlayersTestCase):
    def tick(self, tmux, session_id=None):
        with mock.patch("guild.tmux_windows.Tmux", return_value=tmux):
            return self.cli(["solo", "tick"], session_id)

    def launched_windows(self, tmux):
        return [call[call.index("-n") + 1] for call in tmux.calls if call[0] in ("new-session", "new-window")]

    def launch_events(self):
        return self.db().execute("SELECT payload FROM events WHERE kind = 'solo.launched'").fetchall()

    def test_tick_launches_a_due_player_once_and_posts_to_the_channel(self):
        self.red("ci broke")
        tmux = FakeTmux(True, [], [])
        code, out, err = self.tick(tmux)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.launched_windows(tmux), ["solo-red-main-acme-app"])
        self.assertEqual(len(self.launch_events()), 1)
        self.assertEqual(self.db().execute("SELECT * FROM notices").fetchall(), [])
        self.assertEqual(self.channel_texts(), ["mender (cleric) started on acme/app: main red: ci broke"])

    def test_second_tick_is_debounced_even_without_the_window(self):
        self.red("ci broke")
        self.tick(FakeTmux(True, [], []))
        tmux = FakeTmux(True, [], [])
        self.tick(tmux)
        self.assertEqual(self.launched_windows(tmux), [])
        self.assertEqual(len(self.launch_events()), 1)
        self.assertEqual(self.players()[("acme/app", "red-main")]["state"], "cooling")

    def test_manual_launch_also_debounces_the_tick(self):
        self.red("ci broke")
        self.launch_manually()
        tmux = FakeTmux(True, [], [])
        self.tick(tmux)
        self.assertEqual(self.launched_windows(tmux), [])

    def test_tick_closes_the_window_of_a_finished_player_then_launches(self):
        self.red("ci broke")
        tmux = KillingTmux(True, ["guild"], ["solo-red-main-acme-app"], 0)
        code, out, err = self.tick(tmux)
        self.assertEqual(code, 0, err)
        self.assertEqual(tmux.killed, ["guild:=solo-red-main-acme-app"])
        self.assertLess(tmux.verbs().index("kill-window"), tmux.verbs().index("new-window"))
        self.assertEqual(self.launched_windows(tmux), ["solo-red-main-acme-app"])
        self.assertEqual(len(self.launch_events()), 1)

    def test_tick_leaves_the_window_of_a_running_player_alone(self):
        self.red("ci broke")
        self.cli(["adventurer", "start", "--job", "red-main-acme-app", "--reason", "test reason"], "adv-1")
        tmux = KillingTmux(True, ["guild"], ["solo-red-main-acme-app"], 0)
        code, out, err = self.tick(tmux)
        self.assertEqual(code, 0, err)
        self.assertNotIn("kill-window", tmux.verbs())
        self.assertNotIn("new-window", tmux.verbs())
        self.assertEqual(self.launch_events(), [])

    def test_tick_reports_a_window_it_cannot_close_and_goes_on(self):
        self.red("ci broke")
        tmux = KillingTmux(True, ["guild"], ["solo-red-main-acme-app"], 1)
        code, out, err = self.tick(tmux)
        self.assertEqual(code, 0, err)
        self.assertIn("solo player mender not launched: could not close its finished window", out)
        self.assertNotIn("new-window", tmux.verbs())
        self.assertEqual(self.launch_events(), [])

    def manual_launch(self, tmux):
        with mock.patch("guild.tmux_windows.Tmux", return_value=tmux):
            return self.cli(["solo", "launch", "acme/app", "red-main"], None)

    def test_manual_launch_closes_the_leftover_window_then_launches(self):
        tmux = KillingTmux(True, ["guild"], ["solo-red-main-acme-app"], 0)
        code, out, err = self.manual_launch(tmux)
        self.assertEqual(code, 0, err)
        self.assertEqual(tmux.killed, ["guild:=solo-red-main-acme-app"])
        self.assertLess(tmux.verbs().index("kill-window"), tmux.verbs().index("new-window"))
        self.assertEqual(self.launched_windows(tmux), ["solo-red-main-acme-app"])
        self.assertEqual(len(self.launch_events()), 1)

    def test_manual_launch_refuses_a_running_player(self):
        self.red("ci broke")
        self.cli(["adventurer", "start", "--job", "red-main-acme-app", "--reason", "test reason"], "adv-1")
        self.write_session(os.getpid(), "adv-1", "adv")
        tmux = KillingTmux(True, ["guild"], ["solo-red-main-acme-app"], 0)
        code, out, err = self.manual_launch(tmux)
        self.assertEqual(code, 1)
        self.assertIn("mender is running", err)
        self.assertNotIn("kill-window", tmux.verbs())
        self.assertEqual(self.launch_events(), [])

    def test_manual_launch_refuses_a_stalled_player_with_the_dismiss_hint(self):
        self.red("ci broke")
        self.cli(["adventurer", "start", "--job", "red-main-acme-app", "--reason", "test reason"], "adv-1")
        tmux = KillingTmux(True, ["guild"], ["solo-red-main-acme-app"], 0)
        code, out, err = self.manual_launch(tmux)
        self.assertEqual(code, 1)
        self.assertIn("mender is stalled: run guild adventurer dismiss 1", err)
        self.assertNotIn("kill-window", tmux.verbs())
        self.assertEqual(self.launch_events(), [])

    def test_manual_launch_fails_when_the_leftover_window_cannot_be_closed(self):
        tmux = KillingTmux(True, ["guild"], ["solo-red-main-acme-app"], 1)
        code, out, err = self.manual_launch(tmux)
        self.assertEqual(code, 1)
        self.assertIn("could not close its finished window", err)
        self.assertNotIn("new-window", tmux.verbs())
        self.assertEqual(self.launch_events(), [])

    def launch_args(self, args, tmux, session_id=None):
        with mock.patch("guild.tmux_windows.Tmux", return_value=tmux):
            return self.cli(["solo", "launch", *args], session_id)

    def test_launch_all_launches_every_player_regardless_of_trigger(self):
        tmux = FakeTmux(True, [], [])
        code, out, err = self.launch_args(["--all"], tmux)
        self.assertEqual(code, 0, err)
        self.assertEqual(out.splitlines(), ["mender launched", "{} launched".format(self.dep_name())])
        self.assertEqual(sorted(self.launched_windows(tmux)), ["solo-dependabot-acme-app", "solo-red-main-acme-app"])
        self.assertEqual(len(self.launch_events()), 2)
        self.assertEqual(len(self.channel_texts()), 2)

    def dep_name(self):
        return self.players()[("acme/app", "dependabot")]["name"]

    def test_launch_all_skips_running_and_stalled_and_closes_leftovers(self):
        self.red("ci broke")
        self.cli(["adventurer", "start", "--job", "red-main-acme-app", "--reason", "test reason"], "adv-1")
        tmux = KillingTmux(True, ["guild"], ["solo-dependabot-acme-app"], 0)
        code, out, err = self.launch_args(["--all"], tmux)
        self.assertEqual(code, 0, err)
        self.assertIn("mender skipped: stalled, run guild adventurer dismiss 1", out)
        self.assertIn("{} launched".format(self.dep_name()), out)
        self.assertEqual(tmux.killed, ["guild:=solo-dependabot-acme-app"])
        self.write_session(os.getpid(), "adv-1", "adv")
        code, out, err = self.launch_args(["--all"], KillingTmux(True, ["guild"], [], 0))
        self.assertIn("mender skipped: running", out)

    def test_launch_all_continues_after_a_player_error(self):
        tmux = KillingTmux(True, ["guild"], ["solo-red-main-acme-app", "solo-dependabot-acme-app"], 1)
        code, out, err = self.launch_args(["--all"], tmux)
        self.assertEqual(code, 0, err)
        self.assertEqual(
            out.splitlines(),
            [
                "mender not launched: could not close its finished window",
                "{} not launched: could not close its finished window".format(self.dep_name()),
            ],
        )

    def test_launch_project_limits_players_and_rejects_unknown_project(self):
        tmux = FakeTmux(True, [], [])
        code, out, err = self.launch_args(["--project", "acme"], tmux)
        self.assertEqual(code, 0, err)
        self.assertEqual(len(out.splitlines()), 2)
        code, out, err = self.launch_args(["--project", "nope"], FakeTmux(True, [], []))
        self.assertEqual(code, 1)
        self.assertIn("unknown project 'nope'", err)

    def test_launch_modes_are_exclusive_and_one_is_required(self):
        for args in (["--all", "--project", "acme"], ["acme/app", "red-main", "--all"], [], ["acme/app"]):
            tmux = FakeTmux(True, [], [])
            code, out, err = self.launch_args(args, tmux)
            self.assertEqual(code, 1, args)
            self.assertEqual(self.launched_windows(tmux), [])

    def test_launch_all_refuses_inside_a_session(self):
        tmux = FakeTmux(True, [], [])
        code, out, err = self.launch_args(["--all"], tmux, "sess-1")
        self.assertEqual(code, 1)
        self.assertIn("human terminal", err)
        self.assertEqual(self.launched_windows(tmux), [])

    def test_tick_without_tmux_prints_a_failure_and_records_nothing(self):
        self.red("ci broke")
        code, out, err = self.tick(FakeTmux(False, [], []))
        self.assertEqual(code, 0, err)
        self.assertIn("solo player mender not launched: tmux not found", out)
        self.assertEqual(self.launch_events(), [])

    def test_tick_refuses_inside_a_session(self):
        self.red("ci broke")
        tmux = FakeTmux(True, [], [])
        code, out, err = self.tick(tmux, "sess-1")
        self.assertEqual(code, 1)
        self.assertEqual(tmux.calls, [])

    def test_tick_ignores_idle_cooling_and_running_players(self):
        tmux = FakeTmux(True, [], [])
        self.tick(tmux)
        self.red("ci broke")
        self.finish_job("red-main-acme-app", "none")
        self.cli(["adventurer", "start", "--job", "dependabot-acme-app", "--reason", "test reason"], "adv-2")
        self.db().execute("INSERT OR REPLACE INTO dependabot_status VALUES ('acme/app', 1, 0, 'x')")
        self.tick(tmux)
        self.assertEqual(self.launched_windows(tmux), [])

    def test_launch_events_survive_rebuild(self):
        self.red("ci broke")
        self.tick(FakeTmux(True, [], []))
        before = self.db().execute("SELECT * FROM solo_launches").fetchall()
        self.assertEqual(self.cli(["rebuild"], None)[0], 0)
        after = self.db().execute("SELECT * FROM solo_launches").fetchall()
        self.assertEqual([tuple(r) for r in before], [tuple(r) for r in after])
        self.assertEqual(len(after), 1)


class SoloPlayersBackoffTests(SoloPlayersTestCase):
    def setUp(self):
        super().setUp()
        self.red("ci broke")
        with mock.patch("guild.tmux_windows.Tmux", return_value=FakeTmux(True, [], [])):
            self.cli(["solo", "tick"], None)
        self.finish_job("red-main-acme-app", "could not fix")

    def age(self, hours):
        old = timeutil.to_iso(timeutil.utcnow() - timedelta(hours=hours))
        conn = self.db()
        conn.execute("UPDATE adventurers SET done_at = ?", (old,))
        conn.execute("UPDATE solo_launches SET launched_at = ?", (old,))
        conn.commit()

    def row(self):
        return self.players()[("acme/app", "red-main")]

    def test_launch_records_the_trigger(self):
        self.assertEqual(self.db().execute("SELECT trigger FROM solo_launches").fetchone()[0], "main red: ci broke")

    def test_same_trigger_two_hours_later_is_still_cooling_with_retry_time(self):
        self.age(2)
        row = self.row()
        self.assertEqual(row["state"], "cooling")
        self.assertIsNotNone(row["retry_at"])
        out = self.cli(["board"], None)[1]
        self.assertIn("cooling: same trigger, retry after {}".format(row["retry_at"]), out)

    def test_same_trigger_twenty_five_hours_later_is_due(self):
        self.age(25)
        row = self.row()
        self.assertEqual(row["state"], "due")
        self.assertIsNone(row["retry_at"])

    def test_different_trigger_two_hours_later_is_due(self):
        self.age(2)
        self.red("another failure")
        self.assertEqual(self.row()["state"], "due")

    def test_cooldown_under_one_hour_stays_cooling_for_a_different_trigger(self):
        self.red("another failure")
        row = self.row()
        self.assertEqual(row["state"], "cooling")
        self.assertIsNone(row["retry_at"])

    def test_legacy_launch_event_without_trigger_replays_as_a_different_trigger(self):
        conn = self.db()
        conn.execute(
            "UPDATE events SET payload = ? WHERE kind = 'solo.launched'",
            (json.dumps({"repo": "acme/app", "job": "red-main"}),),
        )
        conn.commit()
        self.assertEqual(self.cli(["rebuild"], None)[0], 0)
        self.assertIsNone(self.db().execute("SELECT trigger FROM solo_launches").fetchone()[0])
        self.age(2)
        self.assertEqual(self.row()["state"], "due")

    def test_manual_launch_without_trigger_records_none(self):
        self.cli(["main", "green", "acme/app"], None)
        with mock.patch("guild.tmux_windows.Tmux", return_value=FakeTmux(True, [], [])):
            self.assertEqual(self.cli(["solo", "launch", "acme/app", "red-main"], None)[0], 0)
        self.assertIsNone(self.db().execute("SELECT trigger FROM solo_launches").fetchone()[0])

    def test_trigger_survives_rebuild(self):
        before = [tuple(r) for r in self.db().execute("SELECT * FROM solo_launches").fetchall()]
        self.assertEqual(self.cli(["rebuild"], None)[0], 0)
        after = [tuple(r) for r in self.db().execute("SELECT * FROM solo_launches").fetchall()]
        self.assertEqual(before, after)


class DependabotSyncTests(SoloPlayersTestCase):
    def setUp(self):
        super().setUp()
        self.write_gh_fixture("dependabot_prs_acme-app", [_GREEN_PR])
        self.write_gh_fixture("dependabot_runs_acme-app", [])

    def sync(self):
        return self.cli(["sync", "--source", "gh"], "sess-1")

    def status(self):
        rows = self.db().execute("SELECT repo, unmergeable, run_failed FROM dependabot_status").fetchall()
        return [tuple(row) for row in rows]

    def kinds(self):
        rows = self.db().execute("SELECT kind FROM events WHERE kind = 'dependabot.synced'").fetchall()
        return len(rows)

    def test_green_dependabot_from_the_start_records_nothing(self):
        self.sync()
        self.assertEqual(self.status(), [])
        self.assertEqual(self.kinds(), 0)

    def test_counts_unmergeable_prs(self):
        prs = [
            _GREEN_PR,
            dict(_GREEN_PR, number=2, mergeable="CONFLICTING"),
            dict(_GREEN_PR, number=3, mergeStateStatus="BEHIND"),
            dict(_GREEN_PR, number=4, mergeStateStatus="DIRTY"),
            dict(_GREEN_PR, number=5, statusCheckRollup=[{"conclusion": "FAILURE"}]),
            dict(_GREEN_PR, number=6, statusCheckRollup=[{"state": "ERROR"}]),
            dict(_GREEN_PR, number=7, statusCheckRollup=[{"conclusion": "SUCCESS"}]),
        ]
        self.write_gh_fixture("dependabot_prs_acme-app", prs)
        self.sync()
        self.assertEqual(self.status(), [("acme/app", 5, 0)])

    def test_latest_run_per_ecosystem_decides_failure(self):
        runs = [
            {"name": "uv in /. - Update #9", "conclusion": ""},
            {"name": "uv in /. - Update #8", "conclusion": "success"},
            {"name": "uv in /. - Update #7", "conclusion": "failure"},
            {"name": "github_actions in /. - Update #6", "conclusion": "failure"},
        ]
        self.write_gh_fixture("dependabot_runs_acme-app", runs)
        self.sync()
        self.assertEqual(self.status(), [("acme/app", 0, 1)])

    def test_unchanged_values_record_no_new_event_and_changes_do(self):
        self.write_gh_fixture("dependabot_prs_acme-app", [dict(_GREEN_PR, mergeable="CONFLICTING")])
        self.sync()
        self.sync()
        self.assertEqual(self.kinds(), 1)
        self.write_gh_fixture("dependabot_prs_acme-app", [_GREEN_PR])
        self.sync()
        self.assertEqual(self.kinds(), 2)
        self.assertEqual(self.status(), [("acme/app", 0, 0)])

    def test_gh_failure_is_reported_and_leaves_status_alone(self):
        self.write_gh_error("dependabot_runs_acme-app", "boom")
        code, out, err = self.sync()
        self.assertIn("acme/app: dependabot check failed: boom", out + err)
        self.assertEqual(self.status(), [])

    def test_repo_without_dependabot_player_is_not_queried(self):
        self.set_players([_RED])
        self.write_gh_error("dependabot_runs_acme-app", "boom")
        code, out, err = self.sync()
        self.assertNotIn("dependabot check failed", out + err)

    def test_rebuild_replays_the_status(self):
        self.write_gh_fixture("dependabot_prs_acme-app", [dict(_GREEN_PR, mergeable="CONFLICTING")])
        self.sync()
        self.cli(["rebuild"], None)
        self.assertEqual(self.status(), [("acme/app", 1, 0)])


class SoloChannelTests(SoloPlayersTestCase):
    def say(self, text, session_id):
        return self.cli(["solo", "say", text], session_id)

    def test_say_is_refused_outside_a_session(self):
        code, out, err = self.say("hello", None)
        self.assertEqual(code, 1)
        self.assertEqual(self.channel_texts(), [])

    def test_say_is_refused_for_a_session_that_is_not_an_adventurer(self):
        code, out, err = self.say("hello", "stranger")
        self.assertEqual(code, 1)
        self.assertEqual(self.channel_texts(), [])

    def test_say_is_refused_for_a_non_solo_adventurer(self):
        self.cli(["adventurer", "start", "fix a thing", "--task", "e/T01", "--reason", "test reason"], "adv-9")
        code, out, err = self.say("hello", "adv-9")
        self.assertEqual(code, 1)
        self.assertIn("solo player", err)
        self.assertEqual(self.channel_texts(), [])

    def test_say_inside_a_solo_session_posts_the_text(self):
        self.start_player("red-main-acme-app", "adv-1")
        code, out, err = self.say("started fixing: lint", "adv-1")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.channel_texts(), ["started fixing: lint"])

    def test_say_strips_control_sequences(self):
        self.start_player("red-main-acme-app", "adv-1")
        self.say("fix \x1b[31mready\x1b[0m", "adv-1")
        self.assertEqual(self.channel_texts(), ["fix ready"])

    def test_say_refuses_empty_text(self):
        self.start_player("red-main-acme-app", "adv-1")
        self.assertEqual(self.say("  \x1b[0m ", "adv-1")[0], 1)
        self.assertEqual(self.channel_texts(), [])

    def test_say_caps_at_300_characters_without_truncating(self):
        self.start_player("red-main-acme-app", "adv-1")
        self.assertEqual(self.say("x" * 301, "adv-1")[0], 1)
        self.assertEqual(self.channel_texts(), [])
        self.assertEqual(self.say("x" * 300, "adv-1")[0], 0)
        self.assertEqual(self.channel_texts(), ["x" * 300])

    def test_manual_launch_posts_a_manual_message(self):
        self.launch_manually()
        self.assertEqual(self.channel_texts(), ["mender (cleric) started on acme/app: manual launch"])

    def test_done_of_a_solo_adventurer_posts_finished(self):
        self.finish_job("red-main-acme-app", "fix PR waits on merge")
        self.assertEqual(self.channel_texts(), ["mender finished: fix PR waits on merge"])

    def test_done_of_a_normal_adventurer_posts_nothing(self):
        self.cli(["adventurer", "start", "fix a thing", "--task", "e/T01", "--reason", "test reason"], "adv-9")
        self.cli(["adventurer", "done", "--pending", "none"], "adv-9")
        self.assertEqual(self.channel_texts(), [])

    def test_channel_lists_newest_first_with_a_limit(self):
        self.start_player("red-main-acme-app", "adv-1")
        for text in ("one", "two", "three"):
            self.say(text, "adv-1")
        code, out, err = self.cli(["solo", "channel", "--limit", "2"], None)
        self.assertEqual(code, 0, err)
        lines = out.strip().splitlines()
        self.assertEqual(len(lines), 3)
        self.assertIn("mender [cleric] three", lines[1])
        self.assertIn("mender [cleric] two", lines[2])

    def test_channel_groups_by_project_and_filters(self):
        self.start_player("red-main-acme-app", "adv-1")
        self.say("one", "adv-1")
        out = self.cli(["solo", "channel", "--limit", "5"], None)[1].splitlines()
        self.assertEqual(out[0], "acme")
        self.assertIn("mender [cleric] one", out[1])
        filtered = self.cli(["solo", "channel", "--limit", "5", "--project", "acme"], None)
        self.assertEqual(filtered[1].splitlines(), out)
        self.assertEqual(self.cli(["solo", "channel", "--limit", "5", "--project", "nope"], None)[0], 1)

    def test_empty_channel_says_so(self):
        self.assertIn("no messages", self.cli(["solo", "channel", "--limit", "5"], None)[1])

    def test_board_carries_the_latest_twenty_messages(self):
        from guild.cli import _build_context
        from guild.commands import board

        self.start_player("red-main-acme-app", "adv-1")
        for number in range(25):
            self.say("m{}".format(number), "adv-1")
        channel = board.board_model(_build_context(None, self.repo_dir))["solo_channel"]
        self.assertEqual(len(channel), 20)
        self.assertEqual(channel[0]["text"], "m24")
        self.assertEqual(
            sorted(channel[0]),
            ["class", "name", "project", "text", "ts"],
        )

    def test_messages_survive_rebuild(self):
        self.start_player("red-main-acme-app", "adv-1")
        self.say("keep me", "adv-1")
        before = [tuple(r) for r in self.db().execute("SELECT * FROM solo_messages").fetchall()]
        self.assertEqual(self.cli(["rebuild"], None)[0], 0)
        after = [tuple(r) for r in self.db().execute("SELECT * FROM solo_messages").fetchall()]
        self.assertEqual(before, after)
        self.assertEqual(len(after), 1)

    def test_message_payload_requires_repo_job_and_text(self):
        self.assertEqual(reducers.required_keys("solo.message"), ("repo", "job", "text"))

    def test_built_in_prompts_tell_the_player_to_post_only_important_messages(self):
        for job in solo_players.JOBS.values():
            self.assertIn("guild solo say", job["prompt"])
            self.assertIn("only important", job["prompt"])


class SoloRunsTests(SoloPlayersTestCase):
    def runs(self):
        return self.players()[("acme/app", "red-main")]["runs"]

    def test_no_runs_before_any_adventurer(self):
        self.assertEqual(self.runs(), [])

    def test_a_done_run_carries_duration_and_pending(self):
        self.finish_job("red-main-acme-app", "all good")
        run = self.runs()[0]
        self.assertEqual(run["state"], "done")
        self.assertEqual(run["pending"], "all good")
        self.assertIsNotNone(run["done_at"])
        self.assertIsNotNone(run["duration"])

    def test_an_active_run_is_stalled_without_a_live_session_and_running_with_one(self):
        self.start_player("red-main-acme-app", "adv-1")
        self.assertEqual(self.runs()[0]["state"], "stalled")
        self.assertIsNone(self.runs()[0]["done_at"])
        self.assertIsNone(self.runs()[0]["duration"])
        with mock.patch("guild.session_info.live_session_ids", return_value={"adv-1"}):
            self.assertEqual(self.runs()[0]["state"], "running")

    def test_runs_are_newest_first_and_limited_to_five(self):
        for number in range(7):
            self.finish_job("red-main-acme-app", "run {}".format(number))
        runs = self.runs()
        self.assertEqual(len(runs), 5)
        self.assertEqual(runs[0]["pending"], "run 6")

    def test_runs_command_prints_one_line_per_run(self):
        self.finish_job("red-main-acme-app", "all good")
        code, out, err = self.cli(["solo", "runs", "acme/app", "red-main"], None)
        self.assertEqual(code, 0, err)
        self.assertIn("done", out)
        self.assertIn("all good", out)

    def test_runs_command_refuses_an_unknown_player(self):
        self.assertEqual(self.cli(["solo", "runs", "acme/app", "nope"], None)[0], 1)
