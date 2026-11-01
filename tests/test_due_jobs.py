import threading
import time
from unittest import mock

from guild import due_jobs, locking
from tests.testutil import GuildTestCase

_REAL_SPAWN = due_jobs.spawn_detached
_SYNC_GH = ("sync", "--source", "gh")
_COMPACT = ("compact",)


class DueJobsTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.state_dir = self.root / "job-state"
        self.calls = []

    def _spawner(self, argv, cwd, low_priority):
        self.calls.append((argv, cwd, low_priority))

    def _spawn_due(self, now_epoch):
        due_jobs.spawn_due(self.state_dir, self.root, now_epoch, self._spawner)

    def test_first_run_spawns_every_job_with_its_argv(self):
        self._spawn_due(1000.0)
        self.assertEqual([call[0] for call in self.calls], [job[0] for job in due_jobs.JOBS.values()])
        self.assertTrue(all(call[1] == self.root for call in self.calls))

    def test_solo_tick_is_a_background_job(self):
        self.assertEqual(due_jobs.JOBS["solo-tick"], (("solo", "tick"), 600, True))

    def test_ticker_spawns_due_jobs_until_stopped(self):
        stop_event = threading.Event()

        def spawner(argv, cwd, low_priority):
            self.calls.append((argv, cwd, low_priority))
            stop_event.set()

        due_jobs.tick_until_stopped(stop_event, 60, self.state_dir, self.root, spawner)
        self.assertEqual(len(self.calls), len(due_jobs.JOBS))

    def test_ticker_returns_at_once_when_already_stopped_and_nothing_due(self):
        stop_event = threading.Event()
        self._spawn_due(time.time())
        self.calls.clear()
        stop_event.set()
        due_jobs.tick_until_stopped(stop_event, 60, self.state_dir, self.root, self._spawner)
        self.assertEqual(self.calls, [])

    def test_low_priority_only_for_heavy_jobs(self):
        self._spawn_due(1000.0)
        priorities = {call[0]: call[2] for call in self.calls}
        self.assertFalse(priorities[_SYNC_GH])
        self.assertTrue(priorities[_COMPACT])

    def test_fresh_stamps_spawn_nothing(self):
        self._spawn_due(1000.0)
        self.calls.clear()
        self._spawn_due(1030.0)
        self.assertEqual(self.calls, [])

    def test_only_elapsed_jobs_spawn_again(self):
        self._spawn_due(1000.0)
        self.calls.clear()
        self._spawn_due(1000.0 + 61)
        self.assertEqual([call[0] for call in self.calls], [("sync", "--source", "bases")])
        self.calls.clear()
        self._spawn_due(1000.0 + 601)
        self.assertEqual(
            [call[0] for call in self.calls],
            [job[0] for name, job in due_jobs.JOBS.items() if name.startswith(("sync", "solo"))],
        )

    def test_stamp_is_touched_before_spawning(self):
        stamps = []

        def spawner(argv, cwd, low_priority):
            stamps.append(sorted(path.name for path in (self.state_dir / "due").iterdir()))

        due_jobs.spawn_due(self.state_dir, self.root, 1000.0, spawner)
        self.assertEqual(stamps[0], ["spawn.lock", "sync-gh"])

    def test_state_dir_is_private(self):
        self._spawn_due(1000.0)
        self.assertEqual((self.state_dir / "due").stat().st_mode & 0o777, 0o700)

    def test_spawn_detached_swallows_launch_failure(self):
        with mock.patch("guild.due_jobs.subprocess.Popen", side_effect=FileNotFoundError("nope")) as popen:
            _REAL_SPAWN(_SYNC_GH, self.root, True)
        self.assertEqual(popen.call_count, 1)

    def test_spawn_detached_drops_the_session_id_from_the_environment(self):
        with mock.patch.dict("os.environ", {"CLAUDE_CODE_SESSION_ID": "sess-1", "KEEP": "1"}):
            with mock.patch("guild.due_jobs.subprocess.Popen") as popen:
                _REAL_SPAWN(_SYNC_GH, self.root, False)
        env = popen.call_args.kwargs["env"]
        self.assertNotIn("CLAUDE_CODE_SESSION_ID", env)
        self.assertEqual(env["KEEP"], "1")

    def test_spawn_detached_lowers_priority_only_when_asked(self):
        with mock.patch("guild.due_jobs.subprocess.Popen") as popen:
            _REAL_SPAWN(_COMPACT, self.root, True)
            _REAL_SPAWN(_COMPACT, self.root, False)
        self.assertIsNotNone(popen.call_args_list[0].kwargs["preexec_fn"])
        self.assertIsNone(popen.call_args_list[1].kwargs["preexec_fn"])
        self.assertEqual(popen.call_args_list[0].args[0][-1:], ["compact"])


class HookTriggersTests(GuildTestCase):
    def _spawned_argvs(self):
        return [argv for argv, _ in self.spawned_jobs]

    def test_session_start_spawns_due_jobs(self):
        self.run_hook("session-start", {"session_id": "s-1", "cwd": str(self.root)})
        self.assertIn(_SYNC_GH, self._spawned_argvs())

    def test_prompt_submit_spawns_due_jobs(self):
        self.run_hook("prompt-submit", {"session_id": "s-1", "cwd": str(self.root)})
        self.assertIn(_SYNC_GH, self._spawned_argvs())

    def test_stop_spawns_due_jobs(self):
        self.run_hook("stop", {"session_id": "s-1", "cwd": str(self.root)})
        self.assertIn(_SYNC_GH, self._spawned_argvs())

    def test_second_hook_inside_interval_spawns_nothing_more(self):
        self.run_hook("stop", {"session_id": "s-1", "cwd": str(self.root)})
        count = len(self.spawned_jobs)
        self.run_hook("prompt-submit", {"session_id": "s-1", "cwd": str(self.root)})
        self.assertEqual(len(self.spawned_jobs), count)


class DueJobsLockTests(GuildTestCase):
    def test_nothing_spawns_while_another_process_holds_the_lock(self):
        state_dir = self.root / "locked-state"
        calls = []
        with locking.try_lock(state_dir / "due", "spawn.lock") as acquired:
            self.assertTrue(acquired)
            due_jobs.spawn_due(state_dir, self.root, 1000.0, lambda argv, cwd, low: calls.append(argv))
        self.assertEqual(calls, [])
