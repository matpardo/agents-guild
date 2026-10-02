import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from guild.cli import main
from tests import fake_acli

_REPO_ROOT = Path(__file__).resolve().parents[1]
_FAKE_GH_SCRIPT = _REPO_ROOT / "tests" / "fake_gh.py"
_FAKE_ACLI_SCRIPT = _REPO_ROOT / "tests" / "fake_acli.py"


class GuildTestCase(unittest.TestCase):
    def setUp(self):
        self._tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tempdir.name)
        self.data_home = self.root / "data"
        self.config_home = self.root / "config"
        self.state_home = self.root / "state"
        self.sessions_dir = self.root / "sessions"
        self.claude_projects_dir = self.root / "claude-projects"
        self.gh_fixtures_dir = self.root / "gh-fixtures"
        self.acli_fixtures_dir = self.root / "acli-fixtures"
        self.bin_dir = self.root / "bin"
        for directory in (
            self.data_home,
            self.config_home,
            self.state_home,
            self.sessions_dir,
            self.claude_projects_dir,
            self.gh_fixtures_dir,
            self.acli_fixtures_dir,
            self.bin_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        gh_wrapper = self.bin_dir / "gh"
        gh_wrapper.write_text("#!/usr/bin/env bash\nexec python3 {} \"$@\"\n".format(_FAKE_GH_SCRIPT))
        gh_wrapper.chmod(0o755)
        acli_wrapper = self.bin_dir / "acli"
        acli_wrapper.write_text("#!/usr/bin/env bash\nexec python3 {} \"$@\"\n".format(_FAKE_ACLI_SCRIPT))
        acli_wrapper.chmod(0o755)

        self._original_environ = dict(os.environ)
        os.environ["XDG_DATA_HOME"] = str(self.data_home)
        os.environ["XDG_CONFIG_HOME"] = str(self.config_home)
        os.environ["XDG_STATE_HOME"] = str(self.state_home)
        os.environ["GUILD_CLAUDE_SESSIONS_DIR"] = str(self.sessions_dir)
        os.environ["GUILD_CLAUDE_PROJECTS_DIR"] = str(self.claude_projects_dir)
        os.environ["GUILD_TEST_GH_DIR"] = str(self.gh_fixtures_dir)
        os.environ["GUILD_TEST_ACLI_DIR"] = str(self.acli_fixtures_dir)
        os.environ["GUILD_ORIGIN"] = "tester@host"
        os.environ["PATH"] = str(self.bin_dir) + os.pathsep + os.environ.get("PATH", "")
        os.environ.pop("CLAUDE_CODE_SESSION_ID", None)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._original_environ)
        self._tempdir.cleanup()

    def write_gh_fixture(self, name, payload):
        (self.gh_fixtures_dir / (name + ".json")).write_text(json.dumps(payload))

    def write_gh_error(self, name, message):
        (self.gh_fixtures_dir / (name + ".err")).write_text(message)

    def write_acli_fixture(self, jql, payload):
        name = fake_acli.fixture_name(jql)
        (self.acli_fixtures_dir / (name + ".json")).write_text(json.dumps(payload))

    def write_acli_error(self, jql, message):
        name = fake_acli.fixture_name(jql)
        (self.acli_fixtures_dir / (name + ".err")).write_text(message)

    def write_project_config(self, name, paths_list, repos):
        config_file = self.root / "{}.json".format(name)
        config_file.write_text(
            json.dumps({"name": name, "paths": paths_list, "github": {"repos": repos}})
        )
        return config_file

    def register_project(self, name, repos):
        project_root = self.root / "projects" / name
        repo_dir = project_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        projects_dir = self.config_home / "guild" / "projects"
        projects_dir.mkdir(parents=True, exist_ok=True)
        (projects_dir / "{}.json".format(name)).write_text(
            json.dumps(
                {"name": name, "paths": [str(project_root) + "/*"], "github": {"repos": repos}}
            )
        )
        return repo_dir

    def run_cli(self, argv, session_id, cwd):
        if session_id is None:
            os.environ.pop("CLAUDE_CODE_SESSION_ID", None)
        else:
            os.environ["CLAUDE_CODE_SESSION_ID"] = session_id
        original_cwd = os.getcwd()
        if cwd is not None:
            os.chdir(str(cwd))
        stdout = io.StringIO()
        stderr = io.StringIO()
        try:
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                try:
                    exit_code = main(argv)
                except SystemExit as system_exit:
                    exit_code = system_exit.code
        finally:
            if cwd is not None:
                os.chdir(original_cwd)
        return exit_code, stdout.getvalue(), stderr.getvalue()

    def run_hook(self, hook_name, stdin_payload):
        stdout = io.StringIO()
        stderr = io.StringIO()
        original_stdin = sys.stdin
        sys.stdin = io.StringIO(json.dumps(stdin_payload))
        try:
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                exit_code = main(["hook", hook_name])
        finally:
            sys.stdin = original_stdin
        return exit_code, stdout.getvalue(), stderr.getvalue()

    def sync_sdd(self, cwd, session_id, project_name, epic, tasks_md_text):
        sdd_root = self.root / "sdd-{}".format(project_name)
        epic_dir = sdd_root / "epics" / epic
        epic_dir.mkdir(parents=True, exist_ok=True)
        (epic_dir / "tasks.md").write_text(tasks_md_text)
        config_file = self.config_home / "guild" / "projects" / "{}.json".format(project_name)
        data = json.loads(config_file.read_text())
        data["sdd"] = {
            "root": str(sdd_root),
            "epics_dir": "epics",
            "task_heading": r"^#{2,3}\s+(T\d+\w*)\b.*?\s[—–-]\s+(.+)$",
            "key_ref": r"[A-Z]{2,10}-\d+",
            "deps_line": r"^\*\*Deps:\*\*\s*(.+)$",
            "status_line": r"^\*\*Status:\*\*\s*(.+)$",
        }
        config_file.write_text(json.dumps(data))
        return self.run_cli(["sync", "--source", "sdd"], session_id, cwd)

    def write_session(self, pid, session_id, name):
        session_file = self.sessions_dir / "{}.json".format(pid)
        session_file.write_text(json.dumps({"pid": pid, "sessionId": session_id, "name": name}))
