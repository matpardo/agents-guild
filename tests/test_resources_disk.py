import shutil
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from guild import db, localbase, paths, probe
from guild.resources import disk
from tests import resources_fixtures as fixtures
from tests.testutil import GuildTestCase

_MIB = 1024 * 1024
_DU_TIMEOUT_SECONDS = 300


def _du_line(size, path):
    return fixtures.ok_result("{}\t{}\n".format(size, path))


class WorktreesTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.clone = self.root / "acme" / "app"
        fixtures.init_clone(self.clone, "acme/app")

    def test_main_checkout_only(self):
        entries = localbase.worktrees(self.clone)
        self.assertEqual(len(entries), 1)
        self.assertEqual(Path(entries[0]["path"]).resolve(), self.clone.resolve())
        self.assertTrue(entries[0]["is_main"])
        self.assertFalse(entries[0]["prunable"])
        self.assertIn(entries[0]["branch"], ("master", "main"))

    def test_linked_worktree_has_branch_and_is_not_main(self):
        linked = self.clone / ".claude" / "worktrees" / "feat-x"
        fixtures.add_worktree(self.clone, linked, "feat-x")
        entries = localbase.worktrees(self.clone)
        self.assertEqual(len(entries), 2)
        self.assertTrue(entries[0]["is_main"])
        self.assertFalse(entries[1]["is_main"])
        self.assertEqual(entries[1]["branch"], "feat-x")
        self.assertEqual(Path(entries[1]["path"]).resolve(), linked.resolve())

    def test_detached_worktree_has_no_branch(self):
        linked = self.root / "detached"
        fixtures.git(self.clone, ["worktree", "add", "-q", "--detach", str(linked)])
        entries = localbase.worktrees(self.clone)
        self.assertIsNone(entries[1]["branch"])

    def test_prunable_worktree_is_flagged(self):
        linked = self.root / "gone"
        fixtures.add_worktree(self.clone, linked, "gone")
        shutil.rmtree(linked)
        entries = localbase.worktrees(self.clone)
        self.assertTrue(entries[1]["prunable"])
        self.assertFalse(entries[0]["prunable"])

    def test_bare_repository_main_has_no_branch(self):
        bare = self.root / "bare.git"
        subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True, capture_output=True)
        entries = localbase.worktrees(bare)
        self.assertEqual(len(entries), 1)
        self.assertTrue(entries[0]["is_main"])
        self.assertIsNone(entries[0]["branch"])

    def test_not_a_repository_is_empty(self):
        plain = self.root / "plain"
        plain.mkdir()
        self.assertEqual(localbase.worktrees(plain), [])


class DeadlineTests(unittest.TestCase):
    def test_not_reached_before_limit(self):
        deadline = disk.Deadline(fixtures.FakeClock([0, 5]), 10)
        self.assertFalse(deadline.reached())

    def test_reached_at_limit(self):
        deadline = disk.Deadline(fixtures.FakeClock([0, 10]), 10)
        self.assertTrue(deadline.reached())


class DuBytesTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.target = self.root / "target"
        self.target.mkdir()
        self.deadline = disk.Deadline(fixtures.FakeClock([0]), 1200)

    def _du(self, responder, excludes):
        runner = fixtures.FakeProbe(responder)
        result = disk.du_bytes(str(self.target), excludes, runner, self.deadline)
        return result, runner

    def test_builds_argv_with_escaped_excludes(self):
        result, runner = self._du(lambda argv: _du_line(10, self.target), ["/a/b [1]/c*", "/a/d?"])
        self.assertEqual(result, (10, "ok"))
        self.assertEqual(
            runner.calls[0]["argv"],
            ["du", "-s", "-B1", "-x", "--exclude=/a/b \\[1]/c\\*", "--exclude=/a/d\\?", "--", str(self.target)],
        )
        self.assertEqual(runner.calls[0]["timeout_seconds"], _DU_TIMEOUT_SECONDS)

    def test_no_excludes_builds_plain_argv(self):
        _, runner = self._du(lambda argv: _du_line(10, self.target), [])
        self.assertEqual(runner.calls[0]["argv"], ["du", "-s", "-B1", "-x", "--", str(self.target)])

    def test_exit_one_with_output_is_accepted(self):
        result, _ = self._du(
            lambda argv: fixtures.failed_result(1, "77\t{}\n".format(self.target), "du: cannot read"), []
        )
        self.assertEqual(result, (77, "ok"))

    def test_exit_one_without_output_is_unavailable(self):
        result, _ = self._du(lambda argv: fixtures.failed_result(1, "", "du: boom"), [])
        self.assertEqual(result, (None, "unavailable"))

    def test_timeout_is_skipped(self):
        result, _ = self._du(lambda argv: fixtures.timeout_result(), [])
        self.assertEqual(result, (None, "skipped"))

    def test_missing_du_binary_is_unavailable(self):
        result, _ = self._du(lambda argv: fixtures.error_result("No such file or directory: 'du'"), [])
        self.assertEqual(result, (None, "unavailable"))

    def test_unparseable_output_is_unavailable(self):
        result, _ = self._du(lambda argv: fixtures.ok_result("garbage\n"), [])
        self.assertEqual(result, (None, "unavailable"))

    def test_missing_path_is_missing_without_running_du(self):
        runner = fixtures.FakeProbe(lambda argv: _du_line(1, "x"))
        result = disk.du_bytes(str(self.root / "gone"), [], runner, self.deadline)
        self.assertEqual(result, (None, "missing"))
        self.assertEqual(runner.calls, [])

    def test_reached_deadline_is_skipped_without_running_du(self):
        deadline = disk.Deadline(fixtures.FakeClock([0, 5000]), 1200)
        runner = fixtures.FakeProbe(lambda argv: _du_line(1, "x"))
        result = disk.du_bytes(str(self.target), [], runner, deadline)
        self.assertEqual(result, (None, "skipped"))
        self.assertEqual(runner.calls, [])


class DiscoverTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.base = self.root / "repos"

    def _project(self, name, repos, patterns):
        return {"name": name, "paths": patterns, "github": {"repos": repos}}

    def test_collects_main_and_linked_worktrees_with_roots(self):
        clone = self.base / "app"
        fixtures.init_clone(clone, "acme/app")
        linked = clone / ".claude" / "worktrees" / "feat-x"
        fixtures.add_worktree(clone, linked, "feat-x")
        project = self._project("acme", ["acme/app"], [str(self.base) + "/*"])
        found = disk.discover([project])
        by_path = {Path(entry["path"]).resolve(): entry for entry in found["entries"]}
        self.assertEqual(set(by_path), {clone.resolve(), linked.resolve()})
        self.assertEqual({entry["project"] for entry in found["entries"]}, {"acme"})
        self.assertEqual({entry["repo"] for entry in found["entries"]}, {"acme/app"})
        roots = {Path(root).resolve() for root in found["roots"]["acme"]}
        self.assertEqual(roots, {clone.resolve(), linked.resolve(), self.base.resolve()})
        checkouts = {Path(path).resolve() for path in found["checkouts"]["acme"]}
        self.assertEqual(checkouts, {clone.resolve(), linked.resolve()})

    def test_path_is_deduped_first_project_alphabetically_wins(self):
        clone = self.base / "app"
        fixtures.init_clone(clone, "acme/app")
        first = self._project("alpha", ["acme/app"], [str(self.base) + "/*"])
        second = self._project("beta", ["acme/app"], [str(self.base) + "/*"])
        found = disk.discover([second, first])
        self.assertEqual([entry["project"] for entry in found["entries"]], ["alpha"])
        self.assertIn(str(clone), found["roots"]["beta"])
        self.assertIn(str(clone), found["checkouts"]["beta"])

    def test_literal_prefix_of_glob_is_a_root_even_without_clones(self):
        project = self._project("acme", ["acme/app"], [str(self.base) + "/team-*/app"])
        found = disk.discover([project])
        self.assertEqual(found["entries"], [])
        self.assertEqual(found["roots"]["acme"], [str(self.base)])
        self.assertEqual(found["checkouts"]["acme"], [])

    def test_clone_is_sampled_even_when_worktree_listing_fails(self):
        clone = self.base / "app"
        fixtures.init_clone(clone, "acme/app")
        project = self._project("acme", ["acme/app"], [str(self.base) + "/*"])
        with mock.patch.object(localbase, "worktrees", return_value=[]):
            found = disk.discover([project])
        self.assertEqual(len(found["entries"]), 1)
        self.assertTrue(found["entries"][0]["is_main"])
        self.assertEqual(found["entries"][0]["path"], str(clone))


class SampleWorktreesTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.conn = db.connect(paths.db_path())
        self.clone = self.root / "acme" / "app"
        fixtures.init_clone(self.clone, "acme/app")
        self.deadline = disk.Deadline(fixtures.FakeClock([0]), 1200)

    def tearDown(self):
        self.conn.close()
        super().tearDown()

    def _entry(self, path, branch, is_main, prunable):
        return {
            "project": "acme",
            "repo": "acme/app",
            "path": str(path),
            "branch": branch,
            "is_main": is_main,
            "prunable": prunable,
        }

    def _pr(self, number, branch, lifecycle):
        self.conn.execute(
            "INSERT INTO prs (repo, number, party, what, lifecycle, branch, seeded) VALUES (?, ?, 'p', 'w', ?, ?, 0)",
            ("acme/app", number, lifecycle, branch),
        )

    def _sample(self, entries, runner):
        return disk.sample_worktrees(self.conn, entries, runner, self.deadline)

    def test_row_shape_and_real_nested_exclusion(self):
        linked = self.clone / ".claude" / "worktrees" / "feat-x"
        fixtures.add_worktree(self.clone, linked, "feat-x")
        fixtures.write_bytes(self.clone / "main.bin", 2 * _MIB)
        fixtures.write_bytes(linked / "big.bin", 8 * _MIB)
        found = disk.discover(
            [{"name": "acme", "paths": [str(self.root / "acme") + "/*"], "github": {"repos": ["acme/app"]}}]
        )
        rows = dict((row[1], row) for _, row in self._sample(found["entries"], probe.run_capture))
        main_row = rows[str(self.clone)]
        linked_row = rows[str(linked)]
        self.assertEqual(main_row[0], "worktree")
        self.assertEqual(main_row[3], "ok")
        self.assertGreaterEqual(linked_row[2], 8 * _MIB)
        self.assertGreaterEqual(main_row[2], 2 * _MIB)
        self.assertLess(main_row[2], 8 * _MIB)
        self.assertEqual(linked_row[5], "feat-x")

    def test_spaces_and_brackets_in_path_are_measured(self):
        clone = self.root / "my app [x]" / "app"
        fixtures.init_clone(clone, "acme/app")
        fixtures.write_bytes(clone / "data.bin", 3 * _MIB)
        entry = self._entry(clone, "main", True, False)
        rows = self._sample([entry], probe.run_capture)
        self.assertEqual(rows[0][1][3], "ok")
        self.assertGreaterEqual(rows[0][1][2], 3 * _MIB)

    def test_nested_worktree_path_is_excluded_in_argv(self):
        linked = self.clone / ".claude" / "worktrees" / "feat-x"
        linked.mkdir(parents=True)
        runner = fixtures.FakeProbe(lambda argv: _du_line(5, argv[-1]))
        self._sample(
            [self._entry(self.clone, "main", True, False), self._entry(linked, "feat-x", False, False)],
            runner,
        )
        main_argv = runner.calls[0]["argv"]
        self.assertIn("--exclude={}".format(linked), main_argv)
        self.assertEqual(main_argv[-1], str(self.clone))
        self.assertFalse([part for part in runner.calls[1]["argv"] if part.startswith("--exclude")])

    def test_prunable_and_vanished_worktrees_are_missing_with_null_bytes(self):
        gone = self.root / "vanished"
        rows = self._sample(
            [self._entry(gone, "old", False, False), self._entry(self.clone, "feat", False, True)],
            fixtures.FakeProbe(lambda argv: _du_line(1, "x")),
        )
        self.assertEqual(
            [row for _, row in rows],
            [
                ["worktree", str(gone), None, "missing", "", "old"],
                ["worktree", str(self.clone), None, "missing", "", "feat"],
            ],
        )

    def test_merged_and_closed_flags_come_from_latest_pr_of_the_branch(self):
        merged = self.root / "w-merged"
        closed = self.root / "w-closed"
        open_pr = self.root / "w-open"
        for path in (merged, closed, open_pr):
            path.mkdir()
        self._pr(1, "feat-a", "merged")
        self._pr(2, "feat-b", "closed")
        self._pr(3, "feat-c", "ready")
        self._pr(4, "feat-d", "closed")
        self._pr(5, "feat-d", "ready")
        reopened = self.root / "w-reopened"
        reopened.mkdir()
        entries = [
            self._entry(merged, "feat-a", False, False),
            self._entry(closed, "feat-b", False, False),
            self._entry(open_pr, "feat-c", False, False),
            self._entry(reopened, "feat-d", False, False),
        ]
        rows = self._sample(entries, fixtures.FakeProbe(lambda argv: _du_line(1, "x")))
        self.assertEqual([row[4] for _, row in rows], ["merged", "closed", "", ""])

    def test_main_and_detached_get_no_flag(self):
        detached = self.root / "w-detached"
        detached.mkdir()
        self._pr(1, "main", "merged")
        rows = self._sample(
            [self._entry(self.clone, "main", True, False), self._entry(detached, None, False, False)],
            fixtures.FakeProbe(lambda argv: _du_line(1, "x")),
        )
        self.assertEqual([row[4] for _, row in rows], ["", ""])
        self.assertEqual(rows[1][1][5], "")

    def test_timeout_row_is_skipped_with_null_bytes(self):
        rows = self._sample(
            [self._entry(self.clone, "main", True, False)], fixtures.FakeProbe(lambda argv: fixtures.timeout_result())
        )
        self.assertEqual(rows[0][1][2:4], [None, "skipped"])

    def test_du_absent_is_unavailable_for_every_item(self):
        other = self.root / "other"
        other.mkdir()
        rows = self._sample(
            [self._entry(self.clone, "main", True, False), self._entry(other, "x", False, False)],
            fixtures.FakeProbe(lambda argv: fixtures.error_result("No such file")),
        )
        self.assertEqual([row[3] for _, row in rows], ["unavailable", "unavailable"])
        self.assertEqual([row[2] for _, row in rows], [None, None])

    def test_deadline_skips_remaining_items(self):
        other = self.root / "other"
        other.mkdir()
        self.deadline = disk.Deadline(fixtures.FakeClock([0, 10, 5000]), 1200)
        runner = fixtures.FakeProbe(lambda argv: _du_line(9, argv[-1]))
        rows = self._sample(
            [self._entry(self.clone, "main", True, False), self._entry(other, "x", False, False)], runner
        )
        self.assertEqual([row[3] for _, row in rows], ["ok", "skipped"])
        self.assertEqual(rows[1][1][2], None)
        self.assertEqual(len(runner.calls), 1)

    def test_rows_carry_their_project(self):
        entry = self._entry(self.clone, "main", True, False)
        entry["project"] = "acme"
        rows = self._sample([entry], fixtures.FakeProbe(lambda argv: _du_line(1, "x")))
        self.assertEqual(rows[0][0], "acme")


if __name__ == "__main__":
    unittest.main()
