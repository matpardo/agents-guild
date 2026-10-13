import json
import os
import subprocess
from datetime import timedelta
from unittest import mock

from guild import timeutil
from guild.cli import _build_context
from guild.commands import dispatch as dispatch_commands
from tests.fake_tmux import FakeTmux
from tests.testutil import GuildTestCase

_PATTERNS = {
    "task_heading": r"^#{2,3}\s+(T\d+\w*)\b.*?\s[—–-]\s+(.+)$",
    "key_ref": r"[A-Z]{2,10}-\d+",
    "deps_line": r"^\*\*Deps:\*\*\s*(.+)$",
    "status_line": r"^\*\*Status:\*\*\s*(.+)$",
}
_NOTIFIED = "acme: sdd_progress alpha/T01 -> notified alpha"


def _git(args, cwd, moment):
    env = dict(os.environ, GIT_AUTHOR_DATE=moment.isoformat(), GIT_COMMITTER_DATE=moment.isoformat())
    result = subprocess.run(["git"] + args, cwd=str(cwd), capture_output=True, text=True, env=env)
    if result.returncode != 0:
        raise AssertionError("git {} failed: {}".format(args, result.stderr))


class SddProgressTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.sdd_root = self.root / "projects" / "acme" / "sdd-docs"
        self.tasks_file = self.sdd_root / "epics" / "widget" / "tasks.md"
        self.tasks_file.parent.mkdir(parents=True)
        self.tasks_file.write_text("## T01 — One\n\n**Deps:** —\n\n**Status:** [ ] pending\n")
        self.real_now = timeutil.utcnow()
        _git(["init", "-q"], self.sdd_root, self.real_now)
        self.commit("first", timedelta(hours=25))
        self.write_block({"sdd_progress": "on"})
        self.run_cli(["party", "start", "alpha"], "sess-1", self.repo_dir)
        self.run_cli(["sync", "--source", "sdd"], "sess-1", self.repo_dir)
        self.pushes = []
        self.run_pass(timedelta(0), False)

    def commit(self, message, age):
        _git(["add", "-A"], self.sdd_root, self.real_now)
        _git(["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", message], self.sdd_root, self.real_now - age)

    def write_block(self, rules):
        path = self.config_home / "guild" / "projects" / "acme.json"
        data = json.loads(path.read_text())
        data["dispatcher"] = {"rules": rules}
        data["sdd"] = dict(_PATTERNS, root=str(self.sdd_root), epics_dir="epics")
        data["notify"] = {"command": ["notify-send", "guild"]}
        path.write_text(json.dumps(data))

    def start_task(self, quest, epic_flag, age):
        self.run_cli(["quest", "add", quest, "--title", quest] + epic_flag, "sess-1", self.repo_dir)
        self.run_cli(["task", "add", quest + "/T01", "--title", "t"], "sess-1", self.repo_dir)
        with mock.patch("guild.timeutil.utcnow", return_value=self.real_now - age):
            code, out, err = self.run_cli(["task", "start", quest + "/T01"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)

    def start_epic_task(self, age):
        self.start_task("alpha", ["--epic", "widget", "--tasks", "T01"], age)

    def run_pass(self, offset, dry_run):
        with mock.patch("guild.timeutil.utcnow", return_value=self.real_now + offset):
            ctx = _build_context(None, self.repo_dir)
            try:
                return dispatch_commands.run(ctx, dry_run, FakeTmux(True, True, {}, 0), self.pushes.append)
            finally:
                ctx.conn.close()

    def notices(self):
        code, out, err = self.run_cli(["notices"], "sess-1", self.repo_dir)
        return [line for line in out.splitlines() if "record progress of" in line]

    def test_stale_task_notifies_once_per_day(self):
        self.start_epic_task(timedelta(hours=25))
        self.assertEqual(self.run_pass(timedelta(0), False), [_NOTIFIED])
        self.assertEqual(self.notices()[0].count("alpha: record progress of T01 in widget tasks.md (no SDD update in 24h)"), 1)
        self.assertEqual(self.pushes, [["notify-send", "guild", "alpha", "sdd-progress"]])
        self.assertEqual(self.run_pass(timedelta(0), False), ["nothing to dispatch"])

    def test_next_day_notifies_again(self):
        self.start_epic_task(timedelta(hours=25))
        self.run_pass(timedelta(0), False)
        self.assertEqual(self.run_pass(timedelta(hours=24), False), [_NOTIFIED])
        self.assertEqual(len(self.notices()), 2)

    def test_recent_sdd_commit_does_nothing(self):
        self.tasks_file.write_text(self.tasks_file.read_text() + "\nnote\n")
        self.commit("progress", timedelta(hours=2))
        self.start_epic_task(timedelta(hours=25))
        self.assertEqual(self.run_pass(timedelta(0), False), ["nothing to dispatch"])

    def test_recent_task_does_nothing(self):
        self.start_epic_task(timedelta(hours=2))
        self.assertEqual(self.run_pass(timedelta(0), False), ["nothing to dispatch"])

    def test_done_task_does_nothing(self):
        self.start_epic_task(timedelta(hours=25))
        self.run_cli(["task", "done", "alpha/T01", "--summary", "s"], "sess-1", self.repo_dir)
        self.assertEqual(self.run_pass(timedelta(0), False), ["nothing to dispatch"])

    def test_non_epic_quest_does_nothing(self):
        self.start_task("solo", ["--no-epic"], timedelta(hours=25))
        self.assertEqual(self.run_pass(timedelta(0), False), ["nothing to dispatch"])

    def test_dry_run_mode_only_plans(self):
        self.write_block({"sdd_progress": "dry-run"})
        self.start_epic_task(timedelta(hours=25))
        self.assertEqual(self.run_pass(timedelta(0), False), ["acme: sdd_progress alpha/T01 -> planned: notify alpha"])
        self.assertEqual(self.notices(), [])

    def test_dry_run_flag_records_nothing(self):
        self.start_epic_task(timedelta(hours=25))
        self.assertEqual(self.run_pass(timedelta(0), True), ["acme: sdd_progress alpha/T01 -> would notify alpha"])
        self.assertEqual(self.notices(), [])
        self.assertEqual(self.pushes, [])

    def test_rule_absent_does_nothing(self):
        self.write_block({})
        self.start_epic_task(timedelta(hours=25))
        self.assertEqual(self.run_pass(timedelta(0), False), ["nothing to dispatch"])
