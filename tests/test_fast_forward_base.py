import json
import os
import sqlite3
import subprocess
from unittest import mock

from guild import config, localbase
from guild.errors import GuildError
from tests.testutil import GuildTestCase

_MERGED_VIEW = {
    "state": "MERGED",
    "isDraft": False,
    "headRefName": "feature/x",
    "title": "t",
    "mergedAt": "2026-01-01T00:00:00Z",
    "statusCheckRollup": [],
}
_OPEN_DRAFT_VIEW = {"state": "OPEN", "isDraft": True, "headRefName": "feature/x", "title": "t"}


def _git(cwd, *args):
    result = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "-C", str(cwd)] + list(args),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise AssertionError("git {} failed: {}".format(args, result.stderr))
    return result.stdout.strip()


class _CloneFixture(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.remote = self.root / "remotes" / "acme" / "app.git"
        self.remote.mkdir(parents=True)
        _git(self.remote, "init", "--bare", "--initial-branch=main")
        self.pusher = self.root / "pusher"
        _git(self.root, "clone", str(self.remote), str(self.pusher))
        self._commit(self.pusher, "seed.txt", "seed")
        _git(self.pusher, "push", "origin", "main")
        _git(self.root, "clone", str(self.remote), str(self.repo_dir))
        self._set_flag(True)
        self.write_gh_fixture("branch_checks_acme-app_main", {"check_runs": []})
        self.run_cli(["party", "start", "alpha", "--reason", "test reason"], "sess-1", self.repo_dir)
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", self.repo_dir)
        self.run_cli(["task", "add", "demo/T01", "--title", "First"], "sess-1", self.repo_dir)
        self._track(1)

    def _commit(self, clone, filename, content):
        (clone / filename).write_text(content)
        _git(clone, "add", filename)
        _git(clone, "commit", "-m", "add " + filename)

    def _config_file(self):
        return self.config_home / "guild" / "projects" / "acme.json"

    def _set_flag(self, value):
        data = json.loads(self._config_file().read_text())
        data["fast_forward_base"] = value
        self._config_file().write_text(json.dumps(data))

    def _track(self, number):
        name = "view_acme-app_{}".format(number)
        self.write_gh_fixture(name, _OPEN_DRAFT_VIEW)
        self.run_cli(
            ["pr", "track", "acme/app#{}".format(number), "--task", "demo/T01", "--what", "x", "--waits", "y"],
            "sess-1",
            self.repo_dir,
        )

    def _merge_upstream(self, filename):
        self._commit(self.pusher, filename, filename)
        _git(self.pusher, "push", "origin", "main")

    def _merge_prs(self, numbers):
        for number in numbers:
            self.write_gh_fixture("view_acme-app_{}".format(number), _MERGED_VIEW)

    def _sync(self):
        code, out, err = self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)

    def _ff_notices(self):
        conn = sqlite3.connect(str(self.data_home / "guild" / "guild.db"))
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM notices WHERE announces LIKE 'ffbase:%'").fetchall()
        conn.close()
        return rows

    def _head(self, ref):
        return _git(self.repo_dir, "rev-parse", ref)


class FastForwardBaseTests(_CloneFixture):
    def test_base_not_checked_out_is_fast_forwarded(self):
        _git(self.repo_dir, "checkout", "-b", "feature")
        self._merge_upstream("one.txt")
        self._merge_prs([1])
        self._sync()
        self.assertEqual(self._head("main"), self._head("origin/main"))
        self.assertEqual(self._ff_notices(), [])

    def test_clean_checked_out_base_is_fast_forwarded(self):
        self._merge_upstream("one.txt")
        self._merge_prs([1])
        self._sync()
        self.assertEqual(self._head("HEAD"), self._head("origin/main"))
        self.assertTrue((self.repo_dir / "one.txt").is_file())
        self.assertEqual(self._ff_notices(), [])

    def test_dirty_checked_out_base_is_left_alone_and_noticed(self):
        before = self._head("main")
        self._merge_upstream("one.txt")
        self._merge_upstream("two.txt")
        (self.repo_dir / "seed.txt").write_text("edited")
        self._merge_prs([1])
        self._sync()
        self.assertEqual(self._head("main"), before)
        rows = self._ff_notices()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["scope"], "project:acme")
        self.assertIn("local main of acme/app 2 commits behind origin, not updated", rows[0]["text"])
        self.assertIn("uncommitted changes", rows[0]["text"])

    def test_untracked_file_does_not_block_fast_forward(self):
        self._merge_upstream("one.txt")
        (self.repo_dir / "editor.lock").write_text("lock")
        self._merge_prs([1])
        self._sync()
        self.assertEqual(self._head("HEAD"), self._head("origin/main"))
        self.assertTrue((self.repo_dir / "editor.lock").is_file())
        self.assertEqual(self._ff_notices(), [])

    def test_untracked_file_clashing_with_incoming_commit_is_noticed(self):
        before = self._head("main")
        self._merge_upstream("one.txt")
        (self.repo_dir / "one.txt").write_text("mine")
        self._merge_prs([1])
        self._sync()
        self.assertEqual(self._head("main"), before)
        rows = self._ff_notices()
        self.assertEqual(len(rows), 1)
        self.assertIn("fast-forward failed", rows[0]["text"])

    def test_diverged_base_is_left_alone_and_noticed(self):
        self._commit(self.repo_dir, "local.txt", "local")
        before = self._head("main")
        self._merge_upstream("one.txt")
        self._merge_prs([1])
        self._sync()
        self.assertEqual(self._head("main"), before)
        rows = self._ff_notices()
        self.assertEqual(len(rows), 1)
        self.assertIn("diverged", rows[0]["text"])

    def test_flag_off_leaves_local_base_untouched(self):
        self._set_flag(False)
        before = self._head("main")
        self._merge_upstream("one.txt")
        self._merge_prs([1])
        self._sync()
        self.assertEqual(self._head("main"), before)
        self.assertEqual(self._ff_notices(), [])

    def test_flag_absent_leaves_local_base_untouched(self):
        data = json.loads(self._config_file().read_text())
        del data["fast_forward_base"]
        self._config_file().write_text(json.dumps(data))
        before = self._head("main")
        self._merge_upstream("one.txt")
        self._merge_prs([1])
        self._sync()
        self.assertEqual(self._head("main"), before)

    def test_two_merges_in_one_run_post_one_notice(self):
        self._track(2)
        self._commit(self.repo_dir, "local.txt", "local")
        self._merge_upstream("one.txt")
        self._merge_prs([1, 2])
        self._sync()
        self.assertEqual(len(self._ff_notices()), 1)

    def test_no_merge_in_run_does_not_touch_local_base(self):
        before = self._head("main")
        self._merge_upstream("one.txt")
        self._sync()
        self.assertEqual(self._head("main"), before)

    def test_linked_worktree_is_not_treated_as_clone(self):
        worktree = self.repo_dir.parent / "linked"
        _git(self.repo_dir, "worktree", "add", "-b", "other", str(worktree))
        _git(self.repo_dir, "checkout", "-b", "feature")
        self._merge_upstream("one.txt")
        self._merge_prs([1])
        self._sync()
        self.assertEqual(self._head("main"), self._head("origin/main"))
        self.assertFalse((worktree / "one.txt").exists())

    def test_ssh_and_https_origin_urls_match_repo(self):
        for url in ("git@github.com:acme/app.git", "https://github.com/acme/app.git"):
            _git(self.repo_dir, "remote", "set-url", "origin", url)
            project = config.load_project(self.config_home / "guild" / "projects", "acme")
            clones = localbase.locate_clones(project)
            self.assertEqual([clone["repo"] for clone in clones], ["acme/app"])

    def test_unrelated_origin_is_ignored(self):
        _git(self.repo_dir, "remote", "set-url", "origin", "git@github.com:other/thing.git")
        project = config.load_project(self.config_home / "guild" / "projects", "acme")
        self.assertEqual(localbase.locate_clones(project), [])


class FastForwardBaseWarningTests(_CloneFixture):
    def setUp(self):
        super().setUp()
        self.home = self.root / "home"
        (self.home / ".claude").mkdir(parents=True)
        env = mock.patch.dict(os.environ, {"HOME": str(self.home)})
        env.start()
        self.addCleanup(env.stop)

    def _fetch_without_update(self):
        self._merge_upstream("one.txt")
        _git(self.repo_dir, "fetch", "origin")

    def test_doctor_warns_when_local_base_is_behind(self):
        self._fetch_without_update()
        code, out, err = self.run_cli(["doctor"], None, None)
        self.assertIn("warn    local main of acme/app is 1 commits behind origin/main", out)

    def test_doctor_silent_when_up_to_date(self):
        code, out, err = self.run_cli(["doctor"], None, None)
        self.assertNotIn("commits behind", out)

    def test_brief_warns_when_local_base_is_behind(self):
        self._fetch_without_update()
        code, out, err = self.run_cli(["brief"], "sess-1", self.repo_dir)
        self.assertIn("local main of acme/app is 1 commits behind origin/main", out)

    def test_brief_does_not_fetch(self):
        self._merge_upstream("one.txt")
        code, out, err = self.run_cli(["brief"], "sess-1", self.repo_dir)
        self.assertNotIn("commits behind", out)


class FastForwardBaseConfigTests(GuildTestCase):
    def _data(self, value):
        return {"name": "acme", "paths": ["/x/*"], "github": {"repos": []}, "fast_forward_base": value}

    def test_boolean_is_accepted(self):
        config.validate_project_config(self._data(True))
        config.validate_project_config(self._data(False))

    def test_non_boolean_is_rejected(self):
        with self.assertRaises(GuildError):
            config.validate_project_config(self._data("yes"))
