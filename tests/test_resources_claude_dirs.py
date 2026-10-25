import os
import unittest
from pathlib import Path
from unittest import mock

from guild import paths, probe
from guild.resources import claude_dirs, disk
from tests import resources_fixtures as fixtures
from tests.testutil import GuildTestCase

_MIB = 1024 * 1024


class EncodeCwdTests(unittest.TestCase):
    def test_every_non_alphanumeric_becomes_a_dash(self):
        cases = {
            "/home/u/acme/app": "-home-u-acme-app",
            "/home/u/acme/app/.claude/worktrees/feat-x": "-home-u-acme-app--claude-worktrees-feat-x",
            "/home/u/my app_v2": "-home-u-my-app-v2",
            "/tmp/a.b/c": "-tmp-a-b-c",
        }
        for path, expected in cases.items():
            with self.subTest(path=path):
                self.assertEqual(paths.encode_cwd(path), expected)


class ClaudeScratchDirTests(unittest.TestCase):
    def test_env_overrides(self):
        with mock.patch.dict(os.environ, {"GUILD_CLAUDE_SCRATCH_DIR": "/home/u/scratch"}):
            self.assertEqual(paths.claude_scratch_dir(), Path("/home/u/scratch"))

    def test_default_is_tmp_claude_uid(self):
        environment = {key: value for key, value in os.environ.items() if key != "GUILD_CLAUDE_SCRATCH_DIR"}
        with mock.patch.dict(os.environ, environment, clear=True):
            self.assertEqual(paths.claude_scratch_dir(), Path("/tmp/claude-{}".format(os.getuid())))


class SampleTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.scratch = self.root / "scratch"
        self.transcripts = self.root / "transcripts"
        self.scratch.mkdir()
        self.transcripts.mkdir()
        self.deadline = disk.Deadline(fixtures.FakeClock([0]), 1200)
        self.app = "/home/u/acme/app"
        self.live = "/home/u/acme/app-live"
        self.worktree = "/home/u/acme/app/.claude/worktrees/feat-x"
        self.entries = [
            self._entry("acme", self.app),
            self._entry("acme", self.worktree),
            self._entry("zeta", self.live),
        ]

    def _entry(self, project, path):
        return {
            "project": project,
            "path": path,
            "repo": "acme/app",
            "branch": "b",
            "is_main": False,
            "prunable": False,
        }

    def _write(self, base, path, session, size):
        fixtures.write_bytes(base / paths.encode_cwd(path) / session / "file.bin", size)

    def _sample(self, runner):
        return claude_dirs.sample(self.entries, self.scratch, self.transcripts, runner, self.deadline)

    def _by_key(self, rows):
        return {(project, row[0], row[1]): row for project, row in rows}

    def test_scratch_and_transcripts_are_sized_per_owner_with_real_du(self):
        self._write(self.scratch, self.app, "s1", 2 * _MIB)
        self._write(self.transcripts, self.app, "s1", 3 * _MIB)
        rows = self._by_key(self._sample(probe.run_capture))
        scratch = rows[("acme", "claude_scratch", self.app)]
        transcripts = rows[("acme", "claude_transcripts", self.app)]
        self.assertEqual((scratch[3], scratch[4], scratch[5]), ("ok", "", ""))
        self.assertGreaterEqual(scratch[2], 2 * _MIB)
        self.assertGreaterEqual(transcripts[2], 3 * _MIB)
        self.assertEqual(len(rows), 2)

    def test_longest_matching_path_wins_across_projects(self):
        self._write(self.scratch, self.live, "s1", _MIB)
        self._write(self.scratch, self.worktree, "s1", _MIB)
        rows = self._by_key(self._sample(probe.run_capture))
        self.assertIn(("zeta", "claude_scratch", self.live), rows)
        self.assertIn(("acme", "claude_scratch", self.worktree), rows)
        self.assertNotIn(("acme", "claude_scratch", self.app), rows)

    def test_unknown_directories_and_loose_files_are_ignored(self):
        (self.scratch / "-home-u-other-thing").mkdir()
        fixtures.write_bytes(self.scratch / "-home-u-other-thing" / "f", 10)
        fixtures.write_bytes(self.scratch / "stray.txt", 10)
        self.assertEqual(self._sample(probe.run_capture), [])

    def test_missing_base_directories_yield_no_rows(self):
        rows = claude_dirs.sample(
            self.entries, self.root / "nope-a", self.root / "nope-b", probe.run_capture, self.deadline
        )
        self.assertEqual(rows, [])

    def test_prefix_collision_attributes_unknown_suffix_to_longest_known_owner(self):
        fixtures.write_bytes(self.scratch / (paths.encode_cwd(self.app) + "-later-session") / "s" / "f", _MIB)
        rows = self._by_key(self._sample(probe.run_capture))
        self.assertIn(("acme", "claude_scratch", self.app), rows)

    def test_several_directories_of_one_owner_are_summed(self):
        self._write(self.scratch, self.app, "s1", _MIB)
        fixtures.write_bytes(self.scratch / (paths.encode_cwd(self.app) + "-extra") / "s" / "f", _MIB)
        calls = []

        def responder(argv):
            calls.append(argv[-1])
            return fixtures.ok_result("100\t{}\n".format(argv[-1]))

        rows = self._by_key(self._sample(fixtures.FakeProbe(responder)))
        self.assertEqual(rows[("acme", "claude_scratch", self.app)][2], 200)
        self.assertEqual(len(calls), 2)

    def test_unmeasured_directory_makes_owner_bytes_null_not_partial(self):
        self._write(self.scratch, self.app, "s1", _MIB)
        rows = self._by_key(self._sample(fixtures.FakeProbe(lambda argv: fixtures.timeout_result())))
        row = rows[("acme", "claude_scratch", self.app)]
        self.assertEqual(row[2:4], [None, "skipped"])

    def test_du_absent_is_unavailable(self):
        self._write(self.scratch, self.app, "s1", _MIB)
        rows = self._by_key(self._sample(fixtures.FakeProbe(lambda argv: fixtures.error_result("No such file"))))
        self.assertEqual(rows[("acme", "claude_scratch", self.app)][2:4], [None, "unavailable"])

    def test_du_runs_without_excludes(self):
        self._write(self.scratch, self.app, "s1", _MIB)
        runner = fixtures.FakeProbe(lambda argv: fixtures.ok_result("1\t{}\n".format(argv[-1])))
        self._sample(runner)
        self.assertFalse([part for part in runner.calls[0]["argv"] if part.startswith("--exclude")])


if __name__ == "__main__":
    unittest.main()
