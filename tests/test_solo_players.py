import json
import os
import sqlite3
from datetime import timedelta
from unittest import mock

from guild import config, paths, solo_players, timeutil
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


class SoloPlayersBoardTests(SoloPlayersTestCase):
    def test_text_board_lists_players_with_launch_command(self):
        self.red("ci down")
        code, out, err = self.cli(["board"], None)
        self.assertEqual(code, 0, err)
        self.assertIn("SOLO PLAYERS", out)
        self.assertIn("mender [cleric] acme/app due main red: ci down", out)
        self.assertIn("guild solo launch acme/app red-main", out)
        self.assertIn("guild solo launch acme/app dependabot", out)

    def test_text_board_without_players_has_no_section(self):
        self.set_players([])
        code, out, err = self.cli(["board"], None)
        self.assertNotIn("SOLO PLAYERS", out)

    def test_solo_list_prints_the_rows(self):
        code, out, err = self.cli(["solo", "list"], None)
        self.assertEqual(code, 0, err)
        self.assertIn("mender [cleric] acme/app red-main idle", out)
        self.assertIn("dependabot [artificer] acme/app dependabot idle", out)

    def test_solo_list_without_players(self):
        self.set_players([])
        self.assertEqual(self.cli(["solo", "list"], None)[1].strip(), "no solo players")


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
