import sys
from unittest import mock

from guild import db, events, paths, timeutil
from guild.cli import _build_context
from guild.commands import handoff as handoff_commands
from tests.testutil import GuildTestCase


class FakeTmux:
    def __init__(self, installed, windows, pane_windows, session_up, create_returncode):
        self._installed = installed
        self.windows = dict(windows)
        self.pane_windows = dict(pane_windows)
        self.session_up = session_up
        self.create_returncode = create_returncode
        self.calls = []

    def installed(self):
        return self._installed

    def run(self, args):
        self.calls.append(list(args))
        verb = args[0]
        if verb == "has-session":
            return (0 if self.session_up else 1), ""
        if verb == "list-windows":
            if not self.session_up:
                return 1, ""
            values = self.windows.keys() if "#{window_id}" in args else self.windows.values()
            return 0, "\n".join(values) + "\n"
        if verb in ("new-window", "new-session"):
            if self.create_returncode != 0:
                return self.create_returncode, ""
            window_id = "@{}".format(len(self.windows) + 1)
            self.windows[window_id] = args[args.index("-n") + 1]
            self.session_up = True
            return 0, window_id + "\n"
        if verb == "display-message":
            pane = args[args.index("-t") + 1]
            if pane not in self.pane_windows:
                return 1, ""
            return 0, self.pane_windows[pane] + "\n"
        if verb in ("kill-window", "kill-pane"):
            return 0, ""
        return 0, ""

    def launch_calls(self):
        return [call for call in self.calls if call[0] in ("new-window", "new-session")]


class RespawnBase(GuildTestCase):
    start_args = ["party", "start", "alpha", "--keeper"]

    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(self.start_args, "sess-1", self.repo_dir)
        self.ctx = _build_context("sess-1", self.repo_dir)
        self.sleeps = 0
        self.bind_after = None
        self.on_sleep = {}

    def tearDown(self):
        self.ctx.conn.close()
        super().tearDown()

    def _record_window(self, generation, window_id):
        with db.writing(self.ctx.conn):
            events.record(
                self.ctx.conn, timeutil.utcnow(), "tester@host", "alpha", None, "acme", "leader.window_launched",
                "local", {"party": "alpha", "generation": generation, "window_id": window_id},
            )

    def _sleep(self, seconds):
        self.sleeps += 1
        if self.bind_after is not None and self.sleeps == self.bind_after:
            self.run_cli(["party", "resume", "alpha"], "sess-2", self.repo_dir)
        if self.sleeps in self.on_sleep:
            self.on_sleep[self.sleeps]()

    def _fake(self, installed=True, windows=None, pane_windows=None, session_up=True, create_returncode=0):
        windows = {"@1": "alpha"} if windows is None else windows
        pane_windows = {"%5": "@1"} if pane_windows is None else pane_windows
        return FakeTmux(installed, windows, pane_windows, session_up, create_returncode)

    def _respawn(self, tmux, pane):
        return handoff_commands.run(self.ctx, "x", "y", None, True, tmux, pane, self._sleep)

    def _state(self):
        return self.ctx.conn.execute("SELECT state FROM parties WHERE name = 'alpha'").fetchone()["state"]

    def _window_rows(self):
        rows = self.ctx.conn.execute("SELECT generation, window_id FROM leader_windows ORDER BY generation").fetchall()
        return [(row["generation"], row["window_id"]) for row in rows]


class RespawnSuccessTests(RespawnBase):
    def test_keeper_respawns_with_remote_control_and_closes_own_window_after_bind(self):
        self._record_window(1, "@1")
        self.bind_after = 2
        tmux = self._fake()
        text, pane_to_close = self._respawn(tmux, "%5")
        self.assertEqual(pane_to_close, "%5")
        self.assertIn("respawned: alpha-g2 bound in window @1; closing this pane", text)
        self.assertIn("note: this text is broadcast to every session", text)
        launch = tmux.launch_calls()[0]
        self.assertEqual(launch[0], "new-window")
        self.assertIn("-n", launch)
        self.assertEqual(launch[launch.index("-n") + 1], "alpha")
        self.assertIn("--remote-control alpha-g2 ", launch[-1])
        self.assertTrue(launch[-1].startswith("GUILD_RESUME=alpha claude -n alpha-g2"))
        self.assertEqual(self.sleeps, 2)
        self.assertEqual(self._window_rows(), [(2, "@2")])

    def test_handoff_is_written_and_party_handed_off_before_launch(self):
        self._record_window(1, "@1")
        self.bind_after = 1
        self._respawn(self._fake(), "%5")
        self.assertTrue((paths.handoffs_dir() / "alpha-g1.md").is_file())

    def test_creates_session_when_absent(self):
        self._record_window(1, "@1")
        self.bind_after = 1
        tmux = self._fake(session_up=False, windows={})
        self._respawn(tmux, "%5")
        self.assertEqual(tmux.launch_calls()[0][0], "new-session")


class RespawnManualCloseTests(RespawnBase):
    def _assert_manual(self, tmux, pane):
        text, pane_to_close = self._respawn(tmux, pane)
        self.assertIsNone(pane_to_close)
        self.assertIn("respawned: alpha-g2 bound; close this window yourself (not a window guild launched)", text)
        self.assertNotIn("kill-window", [call[0] for call in tmux.calls])

    def test_unset_tmux_pane_prints_manual_close_line(self):
        self._record_window(1, "@1")
        self.bind_after = 1
        self._assert_manual(self._fake(), None)

    def test_pane_in_other_window_prints_manual_close_line(self):
        self._record_window(1, "@1")
        self.bind_after = 1
        self._assert_manual(self._fake(pane_windows={"%5": "@7"}), "%5")

    def test_no_recorded_window_prints_manual_close_line(self):
        self.bind_after = 1
        self._assert_manual(self._fake(), "%5")

    def test_recorded_window_gone_from_guild_session_prints_manual_close_line(self):
        self._record_window(1, "@1")
        self.bind_after = 1
        self._assert_manual(self._fake(windows={"@9": "other"}), "%5")

    def test_pane_lookup_failure_prints_manual_close_line(self):
        self._record_window(1, "@1")
        self.bind_after = 1
        self._assert_manual(self._fake(pane_windows={}), "%5")


class RespawnFailureTests(RespawnBase):
    def _assert_kept(self, text, pane_to_close, reason):
        self.assertIsNone(pane_to_close)
        self.assertIn("respawn failed: {}; old session kept".format(reason), text)
        self.assertIn("GUILD_RESUME=alpha claude -n alpha-g2", text)
        self.assertIn("note: this text is broadcast to every session", text)
        self.assertEqual(self._state(), "awaiting-leader")
        self.assertTrue((paths.handoffs_dir() / "alpha-g1.md").is_file())

    def test_tmux_not_installed(self):
        tmux = self._fake(installed=False)
        text, pane_to_close = self._respawn(tmux, "%5")
        self._assert_kept(text, pane_to_close, "tmux not found")
        self.assertEqual(tmux.calls, [])

    def test_window_creation_failure(self):
        self._record_window(1, "@1")
        tmux = self._fake(create_returncode=1)
        text, pane_to_close = self._respawn(tmux, "%5")
        self._assert_kept(text, pane_to_close, "tmux could not create the window")
        self.assertNotIn("kill-window", [call[0] for call in tmux.calls])
        self.assertEqual(self.sleeps, 0)

    def test_missing_cwd(self):
        gone = self.root / "gone"
        self.ctx.conn.execute("UPDATE leaders SET cwd = ? WHERE party = 'alpha'", (str(gone),))
        tmux = self._fake()
        text, pane_to_close = self._respawn(tmux, "%5")
        self._assert_kept(text, pane_to_close, "cwd missing ({})".format(gone))
        self.assertEqual(tmux.launch_calls(), [])

    def test_unknown_cwd(self):
        self.ctx.conn.execute("UPDATE leaders SET cwd = NULL WHERE party = 'alpha'")
        text, pane_to_close = self._respawn(self._fake(), "%5")
        self._assert_kept(text, pane_to_close, "cwd unknown")

    def test_bind_timeout_keeps_old_window_and_leaves_new_one_running(self):
        self._record_window(1, "@1")
        tmux = self._fake()
        text, pane_to_close = self._respawn(tmux, "%5")
        self.assertIsNone(pane_to_close)
        self.assertIn(
            "respawn: next generation did not bind within 90s; old window kept; new window @2 left running", text
        )
        self.assertEqual(self.sleeps, 90)
        self.assertNotIn("kill-window", [call[0] for call in tmux.calls])
        self.assertEqual(self._state(), "awaiting-leader")


class RespawnBindCheckTests(RespawnBase):
    def _no_kill(self, tmux):
        self.assertNotIn("kill-window", [call[0] for call in tmux.calls])
        self.assertNotIn("kill-pane", [call[0] for call in tmux.calls])

    def test_new_window_exiting_aborts_early_and_kills_nothing(self):
        self._record_window(1, "@1")
        tmux = self._fake()
        self.on_sleep[1] = lambda: tmux.windows.pop("@2")
        text, pane_to_close = self._respawn(tmux, "%5")
        self.assertIsNone(pane_to_close)
        self.assertIn("respawn: new window exited before binding; old session kept", text)
        self.assertEqual(self.sleeps, 1)
        self._no_kill(tmux)

    def test_generation_bump_by_the_old_session_is_not_a_bind(self):
        self._record_window(1, "@1")
        tmux = self._fake()
        self.on_sleep[1] = lambda: self.ctx.conn.execute("UPDATE parties SET generation = 2 WHERE name = 'alpha'")
        text, pane_to_close = self._respawn(tmux, "%5")
        self.assertIsNone(pane_to_close)
        self.assertIn("did not bind within 90s", text)
        self._no_kill(tmux)

    def test_missing_party_row_aborts_without_error(self):
        self._record_window(1, "@1")
        tmux = self._fake()
        self.on_sleep[1] = lambda: self.ctx.conn.execute("DELETE FROM parties WHERE name = 'alpha'")
        text, pane_to_close = self._respawn(tmux, "%5")
        self.assertIsNone(pane_to_close)
        self.assertIn("respawn: party 'alpha' is gone or closed; old session kept", text)
        self._no_kill(tmux)

    def test_closed_party_aborts(self):
        self._record_window(1, "@1")
        tmux = self._fake()
        self.on_sleep[1] = lambda: self.ctx.conn.execute("UPDATE parties SET state = 'closed' WHERE name = 'alpha'")
        text, pane_to_close = self._respawn(tmux, "%5")
        self.assertIsNone(pane_to_close)
        self.assertIn("is gone or closed", text)


class RespawnNonKeeperTests(RespawnBase):
    start_args = ["party", "start", "alpha"]

    def test_non_keeper_respawns_without_remote_control(self):
        self._record_window(1, "@1")
        self.bind_after = 1
        tmux = self._fake()
        text, pane_to_close = self._respawn(tmux, "%5")
        self.assertEqual(pane_to_close, "%5")
        self.assertNotIn("--remote-control", tmux.launch_calls()[0][-1])


class RespawnCliTests(RespawnBase):
    def test_handler_prints_before_killing_the_pane(self):
        order = []

        def fake_kill(tmux, pane):
            order.append(("kill", pane, sys.stdout.getvalue()))

        with mock.patch("guild.commands.handoff.run", return_value=("respawned: ok", "%5")), mock.patch(
            "guild.tmux_windows.kill_pane", side_effect=fake_kill
        ), mock.patch.dict("os.environ", {"TMUX_PANE": "%5"}):
            code, out, err = self.run_cli(
                ["handoff", "--respawn", "--in-flight", "x", "--learned", "y"], "sess-1", self.repo_dir
            )
        self.assertEqual(code, 0, err)
        self.assertEqual(len(order), 1)
        self.assertEqual(order[0][1], "%5")
        self.assertIn("respawned: ok", order[0][2])

    def test_handler_kills_only_the_pane_never_the_window(self):
        fake = self._fake()
        with mock.patch("guild.commands.handoff.run", return_value=("respawned: ok", "%5")), mock.patch(
            "guild.tmux_windows.Tmux", return_value=fake
        ):
            self.run_cli(["handoff", "--respawn", "--in-flight", "x", "--learned", "y"], "sess-1", self.repo_dir)
        verbs = [call[0] for call in fake.calls]
        self.assertEqual(fake.calls, [["kill-pane", "-t", "%5"]])
        self.assertNotIn("kill-window", verbs)

    def test_handler_does_not_kill_when_nothing_to_close(self):
        with mock.patch("guild.commands.handoff.run", return_value=("respawn failed", None)), mock.patch(
            "guild.tmux_windows.kill_pane"
        ) as kill:
            self.run_cli(["handoff", "--respawn", "--in-flight", "x", "--learned", "y"], "sess-1", self.repo_dir)
        kill.assert_not_called()

    def test_handler_passes_tmux_pane_from_environment(self):
        with mock.patch("guild.commands.handoff.run", return_value=("t", None)) as run, mock.patch.dict(
            "os.environ", {"TMUX_PANE": "%9"}
        ):
            self.run_cli(["handoff", "--respawn", "--in-flight", "x", "--learned", "y"], "sess-1", self.repo_dir)
        self.assertEqual(run.call_args[0][6], "%9")
        self.assertTrue(run.call_args[0][4])

    def test_prune_rejects_respawn(self):
        code, out, err = self.run_cli(["handoff", "prune", "--respawn"], None, None)
        self.assertEqual(code, 1)
        self.assertIn("--respawn", err)

    def test_dry_run_without_prune_still_rejected_with_respawn(self):
        code, out, err = self.run_cli(
            ["handoff", "--respawn", "--dry-run", "--in-flight", "x", "--learned", "y"], "sess-1", self.repo_dir
        )
        self.assertEqual(code, 1)
