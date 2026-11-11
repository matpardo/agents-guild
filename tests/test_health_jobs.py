import json
import os
import re
import sqlite3
from datetime import timedelta
from pathlib import Path
from unittest import mock

from guild import config, paths, timeutil
from guild.errors import GuildError
from tests.test_revive import FakeTmux
from tests.testutil import GuildTestCase

_BASE = {"name": "acme", "paths": ["/tmp/acme/*"], "github": {"repos": ["acme/app"]}}
_JOB = {"name": "red-main", "command": "/check-main", "every": "1d"}
_ROOT = Path(__file__).resolve().parent.parent


def _with_jobs(jobs):
    return dict(_BASE, health_jobs=jobs)


class HealthJobsConfigTests(GuildTestCase):
    def test_absent_key_is_valid(self):
        config.validate_project_config(_BASE)

    def test_valid_jobs_load(self):
        config.validate_project_config(_with_jobs([_JOB, dict(_JOB, name="drift", every="12h")]))

    def test_invalid_shapes_fail_naming_the_key(self):
        bad = [
            "x",
            {},
            ["x"],
            [{"name": "a", "command": "c"}],
            [dict(_JOB, extra=1)],
            [dict(_JOB, name="../x")],
            [dict(_JOB, name=3)],
            [dict(_JOB, command="")],
            [dict(_JOB, command=["a"])],
            [dict(_JOB, command="-rf")],
            [dict(_JOB, every="soon")],
            [dict(_JOB, every=5)],
            [_JOB, _JOB],
        ]
        for jobs in bad:
            with self.assertRaises(GuildError, msg=jobs) as raised:
                config.validate_project_config(_with_jobs(jobs))
            self.assertIn("health_jobs", raised.exception.message)

    def test_readme_config_example_loads(self):
        config_doc = (_ROOT / "docs" / "configuration.md").read_text()
        section = config_doc.split("## Project config", 1)[1]
        configs = [json.loads(block) for block in re.findall(r"```json\n(.*?)\n```", section, re.S)]
        for data in configs:
            config.validate_project_config(data)
        self.assertTrue(any(data.get("health_jobs") for data in configs))


class HealthJobsTestCase(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.project_dir = self.repo_dir.parent
        self.set_jobs([_JOB, {"name": "drift", "command": "/check-drift", "every": "3d"}])

    def set_jobs(self, jobs):
        path = self.config_home / "guild" / "projects" / "acme.json"
        data = json.loads(path.read_text())
        data["health_jobs"] = jobs
        path.write_text(json.dumps(data))

    def cli(self, argv, session_id):
        return self.run_cli(argv, session_id, self.repo_dir)

    def rows(self, sql):
        conn = sqlite3.connect(str(paths.db_path()))
        conn.row_factory = sqlite3.Row
        self.addCleanup(conn.close)
        return conn.execute(sql).fetchall()

    def board_jobs(self):
        from guild.commands import board

        ctx = self.make_ctx()
        return {job["name"]: job for job in board.board_model(ctx)["health_jobs"]}

    def make_ctx(self):
        from guild.cli import _build_context

        return _build_context(None, self.repo_dir)


class HealthJobStartTests(HealthJobsTestCase):
    def test_start_job_uses_the_job_name_as_text(self):
        code, out, err = self.cli(["adventurer", "start", "--job", "red-main", "--reason", "test reason"], "adv-1")
        self.assertEqual(code, 0, err)
        row = self.rows("SELECT job, health_job, task FROM adventurers")[0]
        self.assertEqual((row["job"], row["health_job"], row["task"]), ("red-main", "red-main", None))

    def test_start_job_refusals(self):
        for argv in (
            ["adventurer", "start", "--job", "nope", "--reason", "test reason"],
            ["adventurer", "start", "text", "--job", "red-main", "--reason", "test reason"],
            ["adventurer", "start", "--job", "red-main", "--task", "e/T01", "--reason", "test reason"],
            ["adventurer", "start", "--reason", "test reason"],
        ):
            code, out, err = self.cli(argv, "adv-1")
            self.assertEqual(code, 1, argv)
        self.assertEqual(self.rows("SELECT * FROM adventurers"), [])

    def test_plain_start_has_no_health_job(self):
        self.cli(
            ["quest", "add", "chore", "--open", "--no-epic", "--title", "c", "--tasks", "T01", "--titles", "one"], None
        )
        self.cli(["adventurer", "start", "fix typo", "--task", "chore/T01", "--reason", "test reason"], "adv-1")
        self.assertIsNone(self.rows("SELECT health_job FROM adventurers")[0]["health_job"])


class HealthJobDueTests(HealthJobsTestCase):
    def test_never_run_job_is_due(self):
        jobs = self.board_jobs()
        self.assertEqual(jobs["red-main"]["state"], "due")
        self.assertIsNone(jobs["red-main"]["last_done"])
        self.assertEqual(jobs["red-main"]["launch"], "guild adventurer launch red-main")
        self.assertEqual(jobs["red-main"]["project"], "acme")

    def test_active_job_is_running_then_ok_after_done(self):
        self.cli(["adventurer", "start", "--job", "red-main", "--reason", "test reason"], "adv-1")
        self.assertEqual(self.board_jobs()["red-main"]["state"], "running")
        self.cli(["adventurer", "done", "--pending", "none"], "adv-1")
        job = self.board_jobs()["red-main"]
        self.assertEqual(job["state"], "ok")
        self.assertIsNotNone(job["last_done"])

    def test_job_is_due_again_after_every(self):
        self.cli(["adventurer", "start", "--job", "red-main", "--reason", "test reason"], "adv-1")
        self.cli(["adventurer", "done", "--pending", "none"], "adv-1")
        old = timeutil.to_iso(timeutil.utcnow() - timedelta(days=2))
        conn = sqlite3.connect(str(paths.db_path()))
        conn.execute("UPDATE adventurers SET done_at = ?", (old,))
        conn.commit()
        conn.close()
        self.assertEqual(self.board_jobs()["red-main"]["state"], "due")

    def test_dismissed_done_still_counts(self):
        self.cli(["adventurer", "start", "--job", "red-main", "--reason", "test reason"], "adv-1")
        self.cli(["adventurer", "done", "--pending", "none"], "adv-1")
        self.cli(["adventurer", "dismiss", "1"], None)
        self.assertEqual(self.board_jobs()["red-main"]["state"], "ok")

    def test_text_board_lists_due_and_running_not_ok(self):
        self.cli(["adventurer", "start", "--job", "red-main", "--reason", "test reason"], "adv-1")
        self.cli(["adventurer", "done", "--pending", "none"], "adv-1")
        self.cli(["adventurer", "dismiss", "1"], None)
        code, out, err = self.cli(["board"], None)
        self.assertEqual(code, 0, err)
        self.assertIn("HEALTH JOBS", out)
        self.assertIn("drift", out)
        self.assertIn("guild adventurer launch drift", out)
        self.assertNotIn("guild adventurer launch red-main", out)

    def test_text_board_without_jobs_has_no_section(self):
        self.set_jobs([])
        code, out, err = self.cli(["board"], None)
        self.assertNotIn("HEALTH JOBS", out)


class HealthJobLaunchTests(HealthJobsTestCase):
    def launch(self, argv, session_id, tmux):
        with mock.patch("guild.tmux_windows.Tmux", return_value=tmux):
            return self.cli(argv, session_id)

    def test_launch_opens_a_window_with_env_prompt_and_cwd(self):
        tmux = FakeTmux(True, [], [])
        code, out, err = self.launch(["adventurer", "launch", "red-main"], None, tmux)
        self.assertEqual(code, 0, err)
        call = next(c for c in tmux.calls if c[0] == "new-session")
        self.assertEqual(call[call.index("-c") + 1], str(self.project_dir))
        command = call[-1]
        self.assertTrue(command.startswith("GUILD_ADVENTURER_JOB=red-main claude "))
        self.assertTrue(command.endswith(" /check-main"))

    def test_launch_stamps_the_session_name_but_not_the_window(self):
        tmux = FakeTmux(True, ["guild"], [])
        self.launch(["adventurer", "launch", "red-main"], None, tmux)
        call = next(c for c in tmux.calls if c[0] == "new-window")
        self.assertEqual(call[call.index("-n") + 1], "health-red-main")
        self.assertRegex(call[-1], r"claude -n health-red-main-\d{8}-\d{6} ")

    def test_launch_quotes_the_command(self):
        self.set_jobs([dict(_JOB, command="check main; rm -rf $HOME")])
        tmux = FakeTmux(True, ["guild"], [])
        self.launch(["adventurer", "launch", "red-main"], None, tmux)
        command = next(c for c in tmux.calls if c[0] == "new-window")[-1]
        self.assertTrue(command.endswith(" 'check main; rm -rf $HOME'"))

    def test_launch_refuses_inside_a_session(self):
        tmux = FakeTmux(True, [], [])
        code, out, err = self.launch(["adventurer", "launch", "red-main"], "sess-1", tmux)
        self.assertEqual(code, 1)
        self.assertEqual(tmux.calls, [])

    def test_launch_refuses_unknown_job_missing_tmux_and_existing_window(self):
        self.assertEqual(self.launch(["adventurer", "launch", "nope"], None, FakeTmux(True, [], []))[0], 1)
        self.assertEqual(self.launch(["adventurer", "launch", "red-main"], None, FakeTmux(False, [], []))[0], 1)
        tmux = FakeTmux(True, ["guild"], ["health-red-main"])
        self.assertEqual(self.launch(["adventurer", "launch", "red-main"], None, tmux)[0], 1)
        self.assertNotIn("new-window", tmux.verbs())


class HealthJobHookTests(HealthJobsTestCase):
    def session_start(self, session_id, job, source):
        with mock.patch.dict(os.environ, {"GUILD_ADVENTURER_JOB": job}):
            return self.run_hook(
                "session-start", {"session_id": session_id, "cwd": str(self.repo_dir), "source": source}
            )

    def test_startup_with_job_env_starts_the_adventurer(self):
        code, out, err = self.session_start("adv-1", "red-main", "startup")
        self.assertEqual(code, 0, err)
        self.assertIn("adventurer 1 started", out)
        self.assertEqual(self.rows("SELECT health_job FROM adventurers")[0]["health_job"], "red-main")
        self.assertEqual(
            self.rows("SELECT reason FROM adventurers")[0]["reason"], "health job red-main launched by the human"
        )

    def test_unknown_job_reports_why(self):
        code, out, err = self.session_start("adv-1", "nope", "startup")
        self.assertIn("GUILD_ADVENTURER_JOB=nope not applied", out)
        self.assertEqual(self.rows("SELECT * FROM adventurers"), [])

    def test_bound_or_already_adventurer_session_is_left_alone(self):
        self.cli(
            ["party", "start", "alpha", "--reason", "test reason", "--goal", "test goal", "--done-when", "test done"],
            "sess-1",
        )
        self.session_start("sess-1", "red-main", "startup")
        self.session_start("adv-1", "red-main", "startup")
        self.session_start("adv-1", "red-main", "compact")
        self.assertEqual(len(self.rows("SELECT * FROM adventurers")), 1)

    def test_non_startup_source_does_not_start(self):
        self.session_start("adv-1", "red-main", "resume")
        self.assertEqual(self.rows("SELECT * FROM adventurers"), [])
