import json
import subprocess

from guild.cli import _build_context
from tests.testutil import GuildTestCase

TIMEOUT_MINUTES = 30
ARGV = ["scripts/cleanup-merged.sh", "--dry-run"]


def ok_result():
    return {"exit_code": 0, "output": "cleaned", "timed_out": False, "error": None, "duration_ms": 12}


def failed_result():
    return {"exit_code": 1, "output": "secret-output", "timed_out": False, "error": None, "duration_ms": 12}


def exit_result(code):
    return {"exit_code": code, "output": "skipped dirty", "timed_out": False, "error": None, "duration_ms": 12}


def timeout_result():
    return {"exit_code": None, "output": "secret-output", "timed_out": True, "error": None, "duration_ms": 12}


def error_result():
    return {"exit_code": None, "output": "", "timed_out": False, "error": "permission denied", "duration_ms": 1}


class FakeRunner:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def __call__(self, argv, cwd, timeout_seconds):
        self.calls.append({"argv": argv, "cwd": cwd, "timeout_seconds": timeout_seconds})
        return self.results.pop(0)


def lifecycle_config(events_configured):
    return {event: {"command": list(ARGV), "timeout_minutes": TIMEOUT_MINUTES} for event in events_configured}


def init_clone(path, repo):
    path.mkdir(parents=True, exist_ok=True)
    for args in (["init"], ["remote", "add", "origin", "https://github.com/{}".format(repo)]):
        subprocess.run(["git", "-C", str(path)] + args, check=True, capture_output=True)


class LifecycleFixture(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        init_clone(self.repo_dir, "acme/app")
        self.set_lifecycle(["on_pr_merged", "on_pr_closed"])
        self.ctx = _build_context("sess-1", self.repo_dir)

    def tearDown(self):
        self.ctx.conn.close()
        super().tearDown()

    def config_file(self):
        return self.config_home / "guild" / "projects" / "acme.json"

    def set_lifecycle(self, events_configured):
        data = json.loads(self.config_file().read_text())
        data["lifecycle"] = lifecycle_config(events_configured)
        self.config_file().write_text(json.dumps(data))

    def set_ok_exit_codes(self, event, codes):
        data = json.loads(self.config_file().read_text())
        data["lifecycle"][event]["ok_exit_codes"] = codes
        self.config_file().write_text(json.dumps(data))

    def project(self):
        return json.loads(self.config_file().read_text())

    def ran_payloads(self):
        rows = self.ctx.conn.execute("SELECT payload FROM events WHERE kind = 'lifecycle.ran' ORDER BY seq").fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def notice_texts(self):
        rows = self.ctx.conn.execute("SELECT text FROM notices ORDER BY id").fetchall()
        return [row["text"] for row in rows]
