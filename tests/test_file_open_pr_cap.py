import json
import sqlite3
import subprocess
from unittest import mock

from guild.adapters import github
from tests.testutil import GuildTestCase

_OPEN_VIEW = {
    "state": "OPEN",
    "isDraft": False,
    "headRefName": "feature/other",
    "title": "t",
    "statusCheckRollup": [{"conclusion": "SUCCESS"}],
    "mergeable": "MERGEABLE",
}


def _diff(paths):
    return {
        "files": [{"path": path} for path in paths],
        "additions": 1,
        "deletions": 1,
        "createdAt": "2026-09-01T10:00:00Z",
    }


class FileOpenPrCapTestCase(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app", "acme/docs"])
        remote = self.root / "remotes" / "acme" / "app.git"
        remote.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
        for command in (
            ["git", "init", "-q", "-b", "main"],
            ["git", "config", "user.email", "t@t.com"],
            ["git", "config", "user.name", "t"],
            ["git", "commit", "--allow-empty", "-q", "-m", "init"],
            ["git", "remote", "add", "origin", str(remote)],
            ["git", "push", "-q", "origin", "main"],
            ["git", "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main"],
            ["git", "checkout", "-q", "-b", "feature/mine"],
        ):
            subprocess.run(command, cwd=str(self.repo_dir), check=True)
        self._set_cap(2)
        self.run_cli(["party", "start", "alpha", "--reason", "test reason"], "sess-1", self.repo_dir)
        self.run_cli(["party", "start", "beta", "--reason", "test reason"], "sess-2", self.repo_dir)
        self.write_gh_fixture("list_feature-mine", [])
        self.write_gh_fixture("branch_checks_acme-app_main", {"check_runs": []})

    def _set_cap(self, cap):
        config_file = self.config_home / "guild" / "projects" / "acme.json"
        data = json.loads(config_file.read_text())
        if cap is None:
            data.pop("max_open_prs_per_file", None)
        else:
            data["max_open_prs_per_file"] = cap
        config_file.write_text(json.dumps(data))

    def _track(self, session_id, number, branch, paths, repo="acme/app"):
        slug = repo.replace("/", "-")
        view = dict(_OPEN_VIEW, headRefName=branch)
        self.write_gh_fixture("view_{}_{}".format(slug, number), dict(view, isDraft=True))
        self.track_legacy_card_pr(
            {"sess-1": "alpha", "sess-2": "beta"}[session_id], repo, number, "ACME-{}".format(number), "x", "y", branch
        )
        self.write_gh_fixture("view_{}_{}".format(slug, number), view)
        self.write_gh_fixture("view_files_{}_{}".format(slug, number), _diff(paths))

    def _sync(self):
        return self.run_cli(["sync", "--source", "gh"], "sess-1", self.repo_dir)

    def _files(self):
        conn = sqlite3.connect(str(self.data_home / "guild" / "guild.db"))
        rows = conn.execute("SELECT number, path FROM pr_files ORDER BY number, path").fetchall()
        conn.close()
        return rows

    def _commit_file(self, relative_path):
        target = self.repo_dir / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("change")
        subprocess.run(["git", "add", relative_path], cwd=str(self.repo_dir), check=True)
        subprocess.run(["git", "commit", "-q", "-m", "change"], cwd=str(self.repo_dir), check=True)

    def _push(self):
        return self.run_hook(
            "pre-push",
            {
                "session_id": "sess-1",
                "tool_input": {"command": "git push origin feature/mine"},
                "cwd": str(self.repo_dir),
            },
        )


class SyncStoresFilesTests(FileOpenPrCapTestCase):
    def test_stores_files_when_configured(self):
        self._track("sess-2", 2, "feature/b", ["a.yml", "b.yml"])
        code, out, err = self._sync()
        self.assertEqual(code, 0, err)
        self.assertEqual(self._files(), [(2, "a.yml"), (2, "b.yml")])

    def test_resync_replaces_files(self):
        self._track("sess-2", 2, "feature/b", ["a.yml", "b.yml"])
        self._sync()
        self.write_gh_fixture("view_files_acme-app_2", _diff(["c.yml"]))
        self._sync()
        self.assertEqual(self._files(), [(2, "c.yml")])

    def test_not_configured_stores_nothing_and_makes_no_diff_call(self):
        self._set_cap(None)
        self._track("sess-2", 2, "feature/b", ["a.yml"])
        with mock.patch.object(github, "pr_diff", wraps=github.pr_diff) as pr_diff:
            self._sync()
        self.assertEqual(pr_diff.call_count, 0)
        self.assertEqual(self._files(), [])

    def test_one_diff_call_per_pr(self):
        self._track("sess-2", 2, "feature/b", ["a.yml"])
        with mock.patch.object(github, "pr_diff", wraps=github.pr_diff) as pr_diff:
            self._sync()
        self.assertEqual(pr_diff.call_count, 1)

    def test_rebuild_replays_files(self):
        self._track("sess-2", 2, "feature/b", ["a.yml"])
        self._sync()
        code, out, err = self.run_cli(["rebuild"], None, self.repo_dir)
        self.assertEqual(code, 0, err)
        self.assertEqual(self._files(), [(2, "a.yml")])

    def test_invalid_cap_is_rejected(self):
        self._set_cap(0)
        code, out, err = self._sync()
        self.assertEqual(code, 1)
        self.assertIn("max_open_prs_per_file", err)


class PrePushFileCapTests(FileOpenPrCapTestCase):
    def setUp(self):
        super().setUp()
        self._track("sess-2", 2, "feature/b", ["a.yml"])
        self._track("sess-2", 3, "feature/c", ["a.yml", "z.yml"])
        self._sync()

    def test_warns_at_cap_with_refs(self):
        self._commit_file("a.yml")
        code, out, err = self._push()
        self.assertEqual(code, 0, err)
        self.assertIn("a.yml: acme/app#2 (beta), acme/app#3 (beta)", out)
        self.assertIn("merge or rebase", out)

    def test_external_blocked_pr_drops_out(self):
        self.run_cli(["pr", "set", "acme/app#2", "--blocked-external", "decision"], "sess-2", self.repo_dir)
        self._commit_file("a.yml")
        code, out, err = self._push()
        self.assertNotIn("merge or rebase", out)

    def test_silent_below_cap(self):
        self._commit_file("z.yml")
        code, out, err = self._push()
        self.assertEqual(code, 0, err)
        self.assertNotIn("merge or rebase", out)

    def test_own_pr_excluded(self):
        self._track("sess-1", 4, "feature/mine", ["a.yml"])
        self._set_cap(3)
        self._sync()
        self._commit_file("a.yml")
        code, out, err = self._push()
        self.assertNotIn("merge or rebase", out)

    def test_merged_pr_drops_out(self):
        self.write_gh_fixture(
            "view_acme-app_3",
            {
                "state": "MERGED",
                "isDraft": False,
                "headRefName": "feature/c",
                "title": "t",
                "mergedAt": "2026-01-01T00:00:00Z",
                "statusCheckRollup": [],
            },
        )
        self._sync()
        self._commit_file("a.yml")
        code, out, err = self._push()
        self.assertNotIn("merge or rebase", out)

    def test_feature_off_is_silent(self):
        self._set_cap(None)
        self._commit_file("a.yml")
        code, out, err = self._push()
        self.assertEqual(code, 0, err)
        self.assertNotIn("merge or rebase", out)

    def test_same_path_in_another_repo_does_not_count(self):
        self._track("sess-2", 5, "feature/d", ["README.md"], "acme/docs")
        self._track("sess-2", 6, "feature/e", ["README.md"], "acme/docs")
        self._sync()
        self._commit_file("README.md")
        code, out, err = self._push()
        self.assertNotIn("merge or rebase", out)

    def test_warning_lists_only_prs_of_the_pushed_repo(self):
        self._track("sess-2", 5, "feature/d", ["a.yml"], "acme/docs")
        self._track("sess-2", 6, "feature/e", ["a.yml"], "acme/docs")
        self.write_gh_fixture("branch_checks_acme-docs_main", {"check_runs": []})
        self._sync()
        subprocess.run(
            ["git", "remote", "set-url", "origin", "git@github.com:acme/docs.git"], cwd=str(self.repo_dir), check=True
        )
        self._commit_file("a.yml")
        code, out, err = self._push()
        self.assertIn("a.yml: acme/docs#5 (beta), acme/docs#6 (beta)", out)
        self.assertNotIn("acme/app#", out)

    def test_unresolvable_repo_is_silent(self):
        subprocess.run(["git", "remote", "remove", "origin"], cwd=str(self.repo_dir), check=True)
        self._commit_file("a.yml")
        code, out, err = self._push()
        self.assertNotIn("merge or rebase", out)
