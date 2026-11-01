import os
import subprocess
from datetime import timedelta

from guild import background, db, party_status, session_status
from guild.cli import _build_context
from tests.testutil import GuildTestCase

_BINDING = {"party": "alpha", "project": "acme", "generation": 1}


class PartyStatusTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.run_cli(["party", "start", "alpha", "--reason", "test reason"], "sess-1", self.repo_dir)
        self.write_session(os.getpid(), "sess-1", "alpha-g1")

    def _kill_session(self):
        (self.sessions_dir / "{}.json".format(os.getpid())).unlink()

    def _hand_off(self):
        self.run_cli(["handoff", "--in-flight", "x", "--learned", "y"], "sess-1", self.repo_dir)

    def _ctx(self):
        return _build_context("sess-1", self.repo_dir)

    def _session(self, kind, payload):
        ctx = self._ctx()
        with db.writing(ctx.conn):
            session_status.record_change(ctx, _BINDING, kind, payload)

    def _waiting(self, wait, message):
        self._session("session.waiting", session_status.waiting_payload(wait, message))

    def _derive(self):
        ctx = self._ctx()
        row = ctx.conn.execute("SELECT * FROM parties WHERE name = 'alpha'").fetchone()
        return party_status.derive(ctx, row)

    def _add_task(self):
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", self.repo_dir)
        self.run_cli(["task", "add", "demo/T01", "--title", "First"], "sess-1", self.repo_dir)

    def _ask(self):
        self.run_cli(["quest", "add", "aq", "--title", "A", "--no-epic"], "sess-1", self.repo_dir)
        self.run_cli(["task", "add", "aq/T01", "--title", "First"], "sess-1", self.repo_dir)
        self.run_cli(["task", "start", "aq/T01"], "sess-1", self.repo_dir)
        self.run_cli(["ask", "ok?", "--context", "x", "--ref", "task:aq/T01"], "sess-1", self.repo_dir)

    def test_closed(self):
        self.run_cli(["party", "close", "--pending", "none"], "sess-1", self.repo_dir)
        self.assertEqual(self._derive(), {"status": "closed", "since": None, "detail": None})

    def test_awaiting_leader_without_work_is_idle(self):
        self._kill_session()
        self._hand_off()
        self.assertEqual(self._derive(), {"status": "idle", "since": None, "detail": None})

    def test_awaiting_leader_with_queued_task_is_queued(self):
        self._add_task()
        self._kill_session()
        self._hand_off()
        self.assertEqual(self._derive(), {"status": "queued", "since": None, "detail": None})

    def test_awaiting_leader_with_live_old_session_is_idle(self):
        self._hand_off()
        self.assertEqual(self._derive()["status"], "idle")

    def test_awaiting_leader_with_live_old_session_and_task_is_queued(self):
        self._add_task()
        self._hand_off()
        self.assertEqual(self._derive()["status"], "queued")

    def test_awaiting_leader_with_open_ask_is_waiting_ask(self):
        self._ask()
        self._kill_session()
        self._hand_off()
        result = self._derive()
        self.assertEqual(result["status"], "waiting-ask")
        self.assertIsNotNone(result["since"])

    def test_answered_pr_ask_without_live_session_is_queued(self):
        self._add_task()
        self.run_cli(["task", "start", "demo/T01"], "sess-1", self.repo_dir)
        self.write_gh_fixture(
            "view_acme-app_1", {"state": "OPEN", "isDraft": True, "headRefName": "feature/x", "title": "t"}
        )
        self.run_cli(
            ["pr", "track", "acme/app#1", "--task", "demo/T01", "--what", "x", "--waits", "y"],
            "sess-1",
            self.repo_dir,
        )
        self.run_cli(["pr", "set", "acme/app#1", "--needs-ask-answer"], "sess-1", self.repo_dir)
        self.run_cli(["ask", "more?", "--context", "c", "--ref", "pr:acme/app#1"], "sess-1", self.repo_dir)
        self.run_cli(["answer", "1", "go"], None, None)
        self._kill_session()
        self.assertEqual(self._derive()["status"], "queued")

    def _hand_off_parked(self, reason):
        self.run_cli(["handoff", "--in-flight", "x", "--learned", "y", "--parked", reason], "sess-1", self.repo_dir)

    def _block_task(self):
        self._add_task()
        self.run_cli(["task", "block", "demo/T01", "--reason", "legal"], "sess-1", self.repo_dir)

    def test_parked_offline_shows_reason_and_age_start(self):
        self._kill_session()
        self._hand_off_parked("legal answer")
        result = self._derive()
        self.assertEqual(result["status"], "parked")
        self.assertEqual(result["detail"], "legal answer")
        self.assertIsNotNone(result["since"])

    def test_open_ask_beats_parked(self):
        self._ask()
        self._kill_session()
        self._hand_off_parked("legal answer")
        self.assertEqual(self._derive()["status"], "waiting-ask")

    def test_parked_beats_queued(self):
        self._add_task()
        self._kill_session()
        self._hand_off_parked("legal answer")
        self.assertEqual(self._derive()["status"], "parked")

    def test_resume_clears_parked(self):
        self._kill_session()
        self._hand_off_parked("legal answer")
        self.write_session(os.getpid(), "sess-2", "alpha-g2")
        self.run_cli(["party", "resume", "alpha"], "sess-2", self.repo_dir)
        self._kill_session()
        self.assertEqual(self._derive()["status"], "idle")

    def test_blocked_only_work_is_blocked_with_groups(self):
        self._block_task()
        self._kill_session()
        self._hand_off()
        result = self._derive()
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["detail"], "1 blocked: 1 — legal")
        self.assertIsNone(result["since"])

    def test_queued_beats_blocked(self):
        self._block_task()
        self.run_cli(["task", "add", "demo/T02", "--title", "Second"], "sess-1", self.repo_dir)
        self._kill_session()
        self._hand_off()
        self.assertEqual(self._derive()["status"], "queued")

    def test_dead_session_with_stale_working_row_is_idle(self):
        self._session("session.working", {})
        self._kill_session()
        self.assertEqual(self._derive()["status"], "idle")

    def test_dead_session_with_stale_working_row_and_task_is_queued(self):
        self._add_task()
        self._session("session.working", {})
        self._kill_session()
        self.assertEqual(self._derive()["status"], "queued")

    def test_dead_session_with_stale_permission_row_is_ignored(self):
        self._waiting("permission", "run ls")
        self._kill_session()
        self.assertEqual(self._derive()["status"], "idle")

    def test_registry_entry_with_dead_pid_is_not_live(self):
        process = subprocess.Popen(["true"])
        process.wait()
        (self.sessions_dir / "{}.json".format(os.getpid())).unlink()
        self.write_session(process.pid, "sess-1", "alpha-g1")
        self._session("session.working", {})
        self.assertEqual(self._derive()["status"], "idle")

    def test_registry_entry_with_dead_pid_and_task_is_queued(self):
        self._add_task()
        process = subprocess.Popen(["true"])
        process.wait()
        (self.sessions_dir / "{}.json".format(os.getpid())).unlink()
        self.write_session(process.pid, "sess-1", "alpha-g1")
        self.assertEqual(self._derive()["status"], "queued")

    def test_session_without_leader_id_is_idle(self):
        ctx = self._ctx()
        with db.writing(ctx.conn):
            ctx.conn.execute("UPDATE parties SET leader_session_id = NULL WHERE name = 'alpha'")
        self.assertEqual(self._derive()["status"], "idle")

    def test_dead_session_with_paused_raid_is_idle(self):
        self._add_task()
        self.run_cli(["raid", "join", "ci", "--until-leave"], "sess-1", self.repo_dir)
        self.run_cli(["raid", "pause", "ci"], "sess-1", self.repo_dir)
        self._kill_session()
        self.assertEqual(self._derive()["status"], "idle")

    def test_permission_beats_ask(self):
        self._ask()
        self._waiting("permission", "run ls")
        result = self._derive()
        self.assertEqual(result["status"], "waiting-permission")
        self.assertEqual(result["detail"], "run ls")
        self.assertIsNotNone(result["since"])

    def test_ask_while_stopped(self):
        self._ask()
        self._session("session.stopped", {})
        result = self._derive()
        self.assertEqual(result["status"], "waiting-ask")
        ask_created = self._ctx().conn.execute("SELECT created_at FROM asks").fetchone()["created_at"]
        self.assertEqual(result["since"], ask_created)

    def test_ask_with_no_session_row(self):
        self._ask()
        self.assertEqual(self._derive()["status"], "waiting-ask")

    def test_ask_with_dead_session_is_waiting_ask(self):
        self._ask()
        self._session("session.working", {})
        self._kill_session()
        self.assertEqual(self._derive()["status"], "waiting-ask")

    def test_ask_while_working_is_working(self):
        self._ask()
        self._session("session.working", {})
        self.assertEqual(self._derive()["status"], "working")

    def test_waiting_input(self):
        self._waiting("idle", "")
        self.assertEqual(self._derive()["status"], "waiting-input")

    def _background(self, key, label):
        background.mark(self._ctx().state_dir, "sess-1", key, label)

    def test_idle_with_pr_wait_is_waiting_background(self):
        self._waiting("idle", "")
        self._background(background.pr_key(os.getpid()), "pr acme/app#7")
        result = self._derive()
        self.assertEqual(result["status"], "waiting-background")
        self.assertEqual(result["detail"], "pr acme/app#7")

    def test_stopped_with_subagent_is_waiting_sub_agents(self):
        self._add_task()
        self._session("session.stopped", {})
        self._background(background.subagent_key("a1"), "a1")
        result = self._derive()
        self.assertEqual((result["status"], result["detail"]), ("waiting-sub-agents", "1 subagents"))

    def test_idle_with_waiting_subagent_is_waiting_sub_agents(self):
        self._waiting("idle", "")
        self._background(background.subagent_key("a1"), background.WAITING_ON_OWN_WORK)
        result = self._derive()
        self.assertEqual((result["status"], result["detail"]), ("waiting-sub-agents", "1 subagents"))

    def test_subagent_beats_pr_wait(self):
        self._waiting("idle", "")
        self._background(background.pr_key(os.getpid()), "pr acme/app#7")
        self._background(background.subagent_key("a1"), "a1")
        result = self._derive()
        self.assertEqual((result["status"], result["detail"]), ("waiting-sub-agents", "1 subagents"))

    def test_open_ask_beats_background(self):
        self._ask()
        self._session("session.stopped", {})
        self._background(background.pr_key(os.getpid()), "pr acme/app#7")
        self.assertEqual(self._derive()["status"], "waiting-ask")

    def test_permission_beats_background(self):
        self._waiting("permission", "ls")
        self._background(background.pr_key(os.getpid()), "pr acme/app#7")
        self.assertEqual(self._derive()["status"], "waiting-permission")

    def test_elicitation_beats_background(self):
        self._waiting("elicitation", "pick")
        self._background(background.subagent_key("a1"), "a1")
        self.assertEqual(self._derive()["status"], "waiting-permission")

    def test_working_ignores_background(self):
        self._session("session.working", {})
        self._background(background.pr_key(os.getpid()), "pr acme/app#7")
        self.assertEqual(self._derive()["status"], "working")

    def test_stopped_with_work(self):
        self._add_task()
        self._session("session.stopped", {})
        result = self._derive()
        self.assertEqual(result["status"], "stopped-with-work")
        self.assertIsNotNone(result["since"])

    def test_stopped_without_work_is_done(self):
        self._session("session.stopped", {})
        self.assertEqual(self._derive()["status"], "done")

    def test_live_session_without_row_is_unknown(self):
        self.assertEqual(self._derive(), {"status": "unknown", "since": None, "detail": None})

    def test_stopped_with_paused_raid_is_done(self):
        self._add_task()
        self.run_cli(["raid", "join", "ci", "--until-leave"], "sess-1", self.repo_dir)
        self.run_cli(["raid", "pause", "ci"], "sess-1", self.repo_dir)
        self._session("session.stopped", {})
        self.assertEqual(self._derive()["status"], "done")

    def test_label_with_age(self):
        self._waiting("permission", "x")
        ctx = self._ctx()
        ctx.now = ctx.now + timedelta(minutes=12, seconds=5)
        status = party_status.derive(ctx, ctx.conn.execute("SELECT * FROM parties").fetchone())
        self.assertEqual(party_status.label(ctx, status), "waiting-permission 12m")

    def test_label_without_since_is_bare_name(self):
        ctx = self._ctx()
        status = {"status": "working", "since": None, "detail": None}
        self.assertEqual(party_status.label(ctx, status), "working")
