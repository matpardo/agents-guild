import io
import json
import sqlite3
import subprocess
import sys
from unittest import mock

from tests.testutil import GuildTestCase


class _ExplodingStdin(io.StringIO):
    def read(self, *args):
        raise AssertionError("pre-commit must not read stdin")


class PreCommitHookTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        for command in (
            ["git", "init", "-q"],
            ["git", "config", "user.email", "t@t.com"],
            ["git", "config", "user.name", "t"],
            ["git", "commit", "--allow-empty", "-q", "-m", "init"],
        ):
            subprocess.run(command, cwd=str(self.repo_dir), check=True)
        config_file = self.config_home / "guild" / "projects" / "acme.json"
        data = json.loads(config_file.read_text())
        data["shared_areas"] = ["config/routes.rb", "db/migrate/*"]
        data["shared_area_claim_ttl"] = "2h"
        config_file.write_text(json.dumps(data))
        self.run_cli(["party", "start", "alpha", "--reason", "test reason"], "sess-1", self.repo_dir)
        self.run_cli(["party", "start", "beta", "--reason", "test reason"], "sess-2", self.repo_dir)

    def _stage(self, directory, relative_path):
        target = directory / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("change")
        subprocess.run(["git", "add", relative_path], cwd=str(directory), check=True)

    def _claims(self):
        conn = sqlite3.connect(str(self.data_home / "guild" / "guild.db"))
        rows = conn.execute("SELECT area, party FROM claims ORDER BY area").fetchall()
        conn.close()
        return rows

    def _pre_commit(self, session_id, cwd):
        with mock.patch.object(sys, "stdin", _ExplodingStdin()):
            return self.run_cli(["hook", "pre-commit"], session_id, cwd)

    def test_bound_party_claims_staged_shared_areas(self):
        self._stage(self.repo_dir, "config/routes.rb")
        self._stage(self.repo_dir, "db/migrate/001_add.rb")
        code, out, err = self._pre_commit("sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        self.assertEqual(self._claims(), [("area:config/routes.rb", "alpha"), ("area:db/migrate/*", "alpha")])

    def test_rejects_commit_when_another_party_holds_an_area(self):
        self._stage(self.repo_dir, "config/routes.rb")
        self._pre_commit("sess-1", self.repo_dir)
        code, out, err = self._pre_commit("sess-2", self.repo_dir)
        self.assertEqual(code, 1)
        self.assertIn("'config/routes.rb' is claimed by party 'alpha'", err)
        self.assertEqual(self._claims(), [("area:config/routes.rb", "alpha")])

    def test_conflict_claims_nothing_for_the_other_staged_areas(self):
        self._stage(self.repo_dir, "config/routes.rb")
        self._pre_commit("sess-1", self.repo_dir)
        self._stage(self.repo_dir, "db/migrate/001_add.rb")
        code, out, err = self._pre_commit("sess-2", self.repo_dir)
        self.assertEqual(code, 1)
        self.assertEqual(self._claims(), [("area:config/routes.rb", "alpha")])

    def test_non_shared_files_pass_without_claims(self):
        self._stage(self.repo_dir, "app/models/user.rb")
        code, out, err = self._pre_commit("sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        self.assertEqual(self._claims(), [])

    def test_unbound_session_passes_without_claims(self):
        self._stage(self.repo_dir, "config/routes.rb")
        code, out, err = self._pre_commit(None, self.repo_dir)
        self.assertEqual(code, 0, err)
        self.assertEqual(self._claims(), [])

    def test_works_inside_a_git_worktree(self):
        worktree = self.root / "projects" / "acme" / "app-wt"
        subprocess.run(["git", "worktree", "add", "-q", "-b", "wt", str(worktree)], cwd=str(self.repo_dir), check=True)
        self.register_project("acme", ["acme/app"])
        config_file = self.config_home / "guild" / "projects" / "acme.json"
        data = json.loads(config_file.read_text())
        data["paths"] = data["paths"] + [str(worktree)]
        data["shared_areas"] = ["config/routes.rb"]
        data["shared_area_claim_ttl"] = "2h"
        config_file.write_text(json.dumps(data))
        self._stage(worktree, "config/routes.rb")
        code, out, err = self._pre_commit("sess-1", worktree)
        self.assertEqual(code, 0, err)
        self.assertEqual(self._claims(), [("area:config/routes.rb", "alpha")])

    def test_outside_a_git_repo_passes(self):
        outside = self.root / "outside"
        outside.mkdir()
        code, out, err = self._pre_commit("sess-1", outside)
        self.assertEqual(code, 0, err)

    def test_internal_error_never_blocks_the_commit(self):
        self._stage(self.repo_dir, "config/routes.rb")
        with mock.patch("guild.commands.hook.pre_commit", side_effect=RuntimeError("boom")):
            code, out, err = self._pre_commit("sess-1", self.repo_dir)
        self.assertEqual(code, 0)
        self.assertIn("guild hook error: boom", err)
