import json
import os
from pathlib import Path
from unittest import mock

from guild import handoff_prune, paths
from guild.cli import _build_context
from tests.testutil import GuildTestCase

_DEAD = "11111111-1111-4111-8111-111111111111"
_LIVE = "22222222-2222-4222-8222-222222222222"
_LEADER = "33333333-3333-4333-8333-333333333333"
_HASH = "0123456789abcdef"
_DAY = 86400


class StatePruneTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha"], _LEADER, self.repo_dir)
        (self.sessions_dir / "live.json").write_text(json.dumps({"sessionId": _LIVE, "name": "x"}))
        self.ctx = _build_context(_LEADER, self.repo_dir)
        self.ctx_dir = self.ctx.state_dir / "ctx"
        self.hints_dir = self.ctx.state_dir / "hints"
        self.ctx_dir.mkdir(parents=True, exist_ok=True)
        self.hints_dir.mkdir(parents=True, exist_ok=True)

    def _marker(self, directory, name, age_seconds):
        path = directory / name
        path.write_text("1")
        stamp = self.ctx.now.timestamp() - age_seconds
        os.utime(str(path), (stamp, stamp))
        return path

    def _plan(self):
        return handoff_prune.plan(self.ctx, paths.handoffs_dir(), self.ctx.state_dir)

    def _marker_actions(self):
        return [action for action in self._plan().actions if action.kind == "marker"]

    def test_dead_markers_of_every_name_shape_are_deleted(self):
        names = [
            (self.ctx_dir, _DEAD),
            (self.hints_dir, _DEAD),
            (self.hints_dir, "nudge-" + _DEAD),
            (self.hints_dir, "resumed-{}-g3".format(_DEAD)),
            (self.hints_dir, "raid-warn-{}-{}".format(_DEAD, _HASH)),
            (self.hints_dir, "raid-pause-{}-{}".format(_DEAD, _HASH)),
            (self.hints_dir, "attended-" + _DEAD),
            (self.hints_dir, "wrapup-" + _DEAD),
        ]
        files = [self._marker(directory, name, 2 * _DAY) for directory, name in names]
        actions = self._marker_actions()
        self.assertEqual(sorted(a.path for a in actions), sorted(files))
        self.assertTrue(all(a.reason == "session not running" for a in actions))
        handoff_prune.apply(self.ctx, self._plan().actions)
        self.assertFalse(any(path.exists() for path in files))

    def test_marker_labels_are_relative_to_state_dir(self):
        self._marker(self.ctx_dir, _DEAD, 2 * _DAY)
        self.assertEqual([a.label for a in self._marker_actions()], ["ctx/" + _DEAD])

    def test_young_marker_is_kept(self):
        self._marker(self.ctx_dir, _DEAD, _DAY - 60)
        self.assertEqual(self._marker_actions(), [])

    def test_marker_exactly_one_day_old_is_deleted(self):
        self._marker(self.ctx_dir, _DEAD, _DAY)
        self.assertEqual(len(self._marker_actions()), 1)

    def test_live_session_marker_is_kept(self):
        self._marker(self.ctx_dir, _LIVE, 5 * _DAY)
        self._marker(self.hints_dir, "nudge-" + _LIVE, 5 * _DAY)
        self._marker(self.hints_dir, "attended-" + _LIVE, 5 * _DAY)
        self._marker(self.hints_dir, "wrapup-" + _LIVE, 5 * _DAY)
        self.assertEqual(self._marker_actions(), [])

    def test_open_party_leader_marker_is_kept(self):
        self._marker(self.ctx_dir, _LEADER, 5 * _DAY)
        self.assertEqual(self._marker_actions(), [])

    def test_closed_party_leader_marker_is_deleted(self):
        self.run_cli(["party", "close", "alpha"], None, None)
        self._marker(self.ctx_dir, _LEADER, 5 * _DAY)
        self.assertEqual(len(self._marker_actions()), 1)

    def test_human_and_unknown_names_are_kept(self):
        self._marker(self.hints_dir, "human", 9 * _DAY)
        self._marker(self.hints_dir, "something-else", 9 * _DAY)
        self._marker(self.ctx_dir, "not-a-uuid", 9 * _DAY)
        self._marker(self.hints_dir, "nudge-" + _DEAD + "-extra", 9 * _DAY)
        self._marker(self.hints_dir, "attended-" + _DEAD + "-extra-junk", 9 * _DAY)
        self.assertEqual(self._marker_actions(), [])

    def test_no_registry_deletes_nothing_and_says_so(self):
        (self.sessions_dir / "live.json").unlink()
        self._marker(self.ctx_dir, _DEAD, 9 * _DAY)
        plan = self._plan()
        self.assertEqual([a for a in plan.actions if a.kind == "marker"], [])
        self.assertIn("markers kept: no session registry", handoff_prune.report_lines(plan, False))

    def test_missing_registry_dir_deletes_nothing(self):
        (self.sessions_dir / "live.json").unlink()
        self.sessions_dir.rmdir()
        self._marker(self.ctx_dir, _DEAD, 9 * _DAY)
        self.assertEqual(self._marker_actions(), [])

    def test_other_state_entries_are_never_scanned(self):
        for name in ("resources", "lifecycle", "locks"):
            directory = self.ctx.state_dir / name
            directory.mkdir(parents=True, exist_ok=True)
            self._marker(directory, _DEAD, 9 * _DAY)
            (directory / "sub.lock").mkdir(exist_ok=True)
        self._marker(self.ctx.state_dir, _DEAD, 9 * _DAY)
        self.assertEqual(self._marker_actions(), [])

    def test_symlinked_marker_is_kept_and_target_untouched(self):
        target = self.root / "precious.txt"
        target.write_text("keep")
        link = self.ctx_dir / _DEAD
        os.symlink(str(target), str(link))
        stamp = self.ctx.now.timestamp() - 9 * _DAY
        os.utime(str(link), (stamp, stamp), follow_symlinks=False)
        self.assertEqual(self._marker_actions(), [])
        self.assertEqual(target.read_text(), "keep")

    def test_directory_named_like_a_marker_is_kept(self):
        (self.hints_dir / _DEAD).mkdir()
        self.assertEqual(self._marker_actions(), [])

    def test_dry_run_report_lists_same_actions_as_real_run(self):
        path = self._marker(self.ctx_dir, _DEAD, 2 * _DAY)
        plan = self._plan()
        dry = handoff_prune.report_lines(plan, True)
        self.assertEqual(dry[0], "handoff prune (dry-run): 0 handoffs, 1 markers")
        self.assertEqual(dry[1], "would delete marker ctx/{}: session not running".format(_DEAD))
        self.assertTrue(path.exists())
        real = handoff_prune.report_lines(plan, False)
        self.assertEqual(real[1], "delete marker ctx/{}: session not running".format(_DEAD))

    def test_marker_vanishing_during_lstat_is_skipped_silently(self):
        self._marker(self.ctx_dir, _DEAD, 2 * _DAY)
        real_stat = Path.lstat

        def vanishing(path, *args, **kwargs):
            if path.name == _DEAD:
                raise FileNotFoundError(str(path))
            return real_stat(path, *args, **kwargs)

        with mock.patch.object(Path, "lstat", autospec=True, side_effect=vanishing):
            self.assertEqual(self._plan().actions, [])

    def test_marker_lstat_permission_error_is_reported_and_others_continue(self):
        self._marker(self.ctx_dir, _DEAD, 2 * _DAY)
        other = self._marker(self.hints_dir, "nudge-" + _DEAD, 2 * _DAY)
        real_stat = Path.lstat

        def denied(path, *args, **kwargs):
            if path.parent.name == "ctx" and path.name == _DEAD:
                raise PermissionError("denied")
            return real_stat(path, *args, **kwargs)

        with mock.patch.object(Path, "lstat", autospec=True, side_effect=denied):
            actions = self._plan().actions
        self.assertEqual(
            sorted((a.verb, a.reason) for a in actions), [("delete", "session not running"), ("skip", "denied")]
        )
        self.assertIn(other, [a.path for a in actions])

    def test_marker_unlink_failure_is_reported_and_others_continue(self):
        first = self._marker(self.ctx_dir, _DEAD, 2 * _DAY)
        second = self._marker(self.hints_dir, _DEAD, 2 * _DAY)
        actions = self._plan().actions
        real_unlink = Path.unlink

        def flaky(path, missing_ok):
            if path == first:
                raise PermissionError("denied")
            return real_unlink(path, missing_ok=missing_ok)

        with mock.patch.object(Path, "unlink", autospec=True, side_effect=flaky):
            result = handoff_prune.apply(self.ctx, actions)
        self.assertEqual([a.reason for a in result.skipped], ["denied"])
        self.assertTrue(first.exists())
        self.assertFalse(second.exists())
