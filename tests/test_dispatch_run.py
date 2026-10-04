import json
from datetime import timedelta
from unittest import mock

from guild import db, dispatch_rules, events, locking, timeutil
from guild.cli import _build_context
from guild.commands import dispatch as dispatch_commands
from tests.fake_tmux import FakeTmux
from tests.testutil import GuildTestCase


def _ask_trigger(conn, projects, event):
    if event["kind"] != "ask.answered":
        return None
    return dispatch_rules.Trigger(
        "acme",
        "ask_answered",
        "ask_answered:{}".format(event["payload"]["id"]),
        "alpha",
        "ask #{}".format(event["payload"]["id"]),
        "prompt",
    )


class DispatchRunBase(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.register_project("beta", ["beta/app"])
        self.set_block({"ask_answered": "dry-run"})
        self.pushes = []
        self.run_cli(["party", "start", "alpha"], "sess-1", self.repo_dir)
        self.run_cli(["handoff", "--in-flight", "x", "--learned", "y"], "sess-1", self.repo_dir)
        patcher = mock.patch.dict(dispatch_rules.RULES, {"ask_answered": _ask_trigger}, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def set_block(self, rules):
        path = self.config_home / "guild" / "projects" / "acme.json"
        data = json.loads(path.read_text())
        data["dispatcher"] = {"permission_mode": "acceptEdits", "max_launches_per_hour": 3, "rules": rules}
        path.write_text(json.dumps(data))

    def remove_block(self):
        path = self.config_home / "guild" / "projects" / "acme.json"
        data = json.loads(path.read_text())
        del data["dispatcher"]
        path.write_text(json.dumps(data))

    def ctx(self):
        ctx = _build_context(None, self.repo_dir)
        self.addCleanup(ctx.conn.close)
        return ctx

    def answered(self, ask_id, age):
        ctx = self.ctx()
        with db.writing(ctx.conn):
            return events.record(
                ctx.conn, ctx.now - age, ctx.origin, "alpha", None, "acme", "ask.answered", "guild",
                {"id": ask_id, "answer": "x"},
            )["seq"]

    def run_pass(self, dry_run):
        ctx = self.ctx()
        return dispatch_commands.run(ctx, dry_run, FakeTmux(True, True, {}, 0), self.pushes.append)

    def cursor(self, project):
        row = self.ctx().conn.execute(
            "SELECT last_seq FROM dispatch_cursors WHERE project = ?", (project,)
        ).fetchone()
        return None if row is None else row["last_seq"]

    def max_seq(self):
        return events.max_seq(self.ctx().conn)

    def event_count(self):
        return self.ctx().conn.execute("SELECT COUNT(*) AS n FROM events").fetchone()["n"]

    def decisions(self):
        return [dict(row) for row in self.ctx().conn.execute("SELECT * FROM dispatch_decisions").fetchall()]


class FirstPassTests(DispatchRunBase):
    def test_first_pass_initializes_cursor_and_decides_nothing_about_earlier_events(self):
        seq = self.answered(1, timedelta(minutes=1))
        lines = self.run_pass(False)
        self.assertEqual(lines, ["acme: cursor initialized at seq {}".format(seq)])
        self.assertEqual(self.cursor("acme"), seq)
        self.assertEqual(self.decisions(), [])

    def test_project_without_block_has_no_cursor(self):
        self.assertEqual(self.run_pass(False), ["acme: cursor initialized at seq {}".format(self.max_seq())])
        self.assertIsNone(self.cursor("beta"))

    def test_no_enabled_project_prints_nothing_to_dispatch(self):
        self.remove_block()
        self.assertEqual(self.run_pass(False), ["nothing to dispatch"])

    def test_removing_the_block_deletes_the_cursor_and_readding_reinitializes_later(self):
        self.run_pass(False)
        self.assertIsNotNone(self.cursor("acme"))
        self.remove_block()
        self.run_pass(False)
        self.assertIsNone(self.cursor("acme"))
        old = self.answered(1, timedelta(minutes=1))
        self.set_block({"ask_answered": "dry-run"})
        lines = self.run_pass(False)
        self.assertEqual(lines, ["acme: cursor initialized at seq {}".format(old)])
        self.assertEqual(self.decisions(), [])


class SecondPassTests(DispatchRunBase):
    def setUp(self):
        super().setUp()
        self.run_pass(False)

    def test_event_after_cursor_is_decided_and_cursor_advances(self):
        seq = self.answered(7, timedelta(minutes=1))
        lines = self.run_pass(False)
        self.assertEqual(lines, ["acme: ask_answered ask #7 -> planned: launch alpha g2 (dry-run, mode acceptEdits)"])
        self.assertEqual(self.cursor("acme"), seq)
        self.assertEqual([row["key"] for row in self.decisions()], ["ask_answered:7"])

    def test_second_pass_over_the_same_events_decides_nothing(self):
        self.answered(7, timedelta(minutes=1))
        self.run_pass(False)
        self.assertEqual(self.run_pass(False), ["nothing to dispatch"])
        self.assertEqual(len(self.decisions()), 1)

    def test_cursor_advances_past_events_without_triggers(self):
        ctx = self.ctx()
        with db.writing(ctx.conn):
            last = events.record(
                ctx.conn, ctx.now, ctx.origin, None, None, None, "notice.seen", "guild", {"id": 1}
            )["seq"]
        self.run_pass(False)
        self.assertEqual(self.cursor("acme"), last)

    def test_events_older_than_an_hour_are_ignored_and_counted(self):
        self.answered(1, timedelta(hours=2))
        self.answered(2, timedelta(hours=3))
        lines = self.run_pass(False)
        self.assertEqual(lines, ["acme: 2 events older than 1h ignored"])
        self.assertEqual(self.decisions(), [])

    def test_rule_absent_from_config_is_ignored_silently(self):
        self.set_block({})
        self.answered(1, timedelta(minutes=1))
        self.assertEqual(self.run_pass(False), ["nothing to dispatch"])

    def test_trigger_for_a_project_without_block_is_ignored(self):
        self.remove_block()
        self.answered(1, timedelta(minutes=1))
        self.assertEqual(self.run_pass(False), ["nothing to dispatch"])


class LockTests(DispatchRunBase):
    def test_held_lock_prints_message_and_writes_nothing(self):
        before = self.event_count()
        ctx = self.ctx()
        with locking.try_lock(ctx.state_dir / "dispatch", "dispatch.lock") as acquired:
            self.assertTrue(acquired)
            lines = self.run_pass(False)
        self.assertEqual(lines, ["another dispatch pass is running"])
        self.assertEqual(self.event_count(), before)
        self.assertIsNone(self.cursor("acme"))


class DryRunTests(DispatchRunBase):
    def test_dry_run_does_not_initialize_the_cursor(self):
        self.answered(1, timedelta(minutes=1))
        lines = self.run_pass(True)
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith("acme: would initialize cursor at seq "))
        self.assertIsNone(self.cursor("acme"))

    def test_dry_run_leaves_events_and_cursor_unchanged_and_prints_would(self):
        self.run_pass(False)
        seq = self.answered(7, timedelta(minutes=1))
        before = self.event_count()
        cursor_before = self.cursor("acme")
        lines = self.run_pass(True)
        self.assertEqual(lines, ["acme: ask_answered ask #7 -> would plan launch alpha g2 (mode acceptEdits)"])
        self.assertEqual(self.event_count(), before)
        self.assertEqual(self.cursor("acme"), cursor_before)
        self.assertLess(cursor_before, seq)

    def test_dry_run_does_not_take_the_lock(self):
        ctx = self.ctx()
        with locking.try_lock(ctx.state_dir / "dispatch", "dispatch.lock") as acquired:
            self.assertTrue(acquired)
            lines = self.run_pass(True)
        self.assertNotIn("another dispatch pass is running", lines)

    def test_dry_run_counts_old_events(self):
        self.run_pass(False)
        self.answered(1, timedelta(hours=2))
        self.assertEqual(self.run_pass(True), ["acme: 1 events older than 1h ignored"])


class CliTests(DispatchRunBase):
    def test_cli_without_enabled_project_prints_nothing_to_dispatch(self):
        self.remove_block()
        code, out, err = self.run_cli(["dispatch", "run"], None, self.repo_dir)
        self.assertEqual((code, out), (0, "nothing to dispatch\n"))

    def test_cli_dry_run_flag(self):
        code, out, err = self.run_cli(["dispatch", "run", "--dry-run"], None, self.repo_dir)
        self.assertEqual(code, 0)
        self.assertIn("acme: would initialize cursor at seq {}".format(self.max_seq()), out)

    def test_invalid_dispatcher_block_exits_with_error(self):
        path = self.config_home / "guild" / "projects" / "acme.json"
        data = json.loads(path.read_text())
        data["dispatcher"]["permission_mode"] = "bypassPermissions"
        path.write_text(json.dumps(data))
        code, out, err = self.run_cli(["dispatch", "run"], None, self.repo_dir)
        self.assertEqual(code, 1)
        self.assertIn("dispatcher.permission_mode", err)


class StatusTests(DispatchRunBase):
    def _decide(self, key, mode, outcome, party, generation, subject, reason, ts):
        ctx = self.ctx()
        with db.writing(ctx.conn):
            events.record(
                ctx.conn, ts, ctx.origin, party, None, "acme", "dispatch.decided", "local",
                {
                    "project": "acme", "rule": key.split(":")[0], "key": key, "mode": mode, "outcome": outcome,
                    "party": party, "generation": generation, "permission_mode": "acceptEdits",
                    "subject": subject, "reason": reason,
                },
            )

    def test_status_golden(self):
        self.set_block({"ask_answered": "on", "checks_failing": "dry-run"})
        self.run_pass(False)
        ctx = self.ctx()
        now = ctx.now
        self._decide("checks_failing:acme/app#7:abc", "dry-run", "planned", "beta", 3, "acme/app#7", None, now - timedelta(minutes=30))
        self._decide("ask_answered:12", "on", "launching", "alpha", 5, "ask #12", None, now - timedelta(minutes=3))
        with db.writing(ctx.conn):
            events.record(
                ctx.conn, now, ctx.origin, "alpha", None, "acme", "dispatch.launched", "local",
                {"project": "acme", "key": "ask_answered:12", "party": "alpha", "generation": 5, "window_id": "@12"},
            )
        self._decide("ask_answered:13", "on", "skipped", "beta", 3, "ask #13", "party not handed off", now - timedelta(minutes=1))
        lines = dispatch_commands.status(self.ctx())
        stamp = lambda delta: (now - delta).strftime("%Y-%m-%dT%H:%M")
        self.assertEqual(
            lines,
            [
                "acme: cursor {} | launches last hour 1/3 | mode acceptEdits".format(self.cursor("acme")),
                "  ask_answered: on",
                "  checks_failing: dry-run",
                "  in flight: alpha g5 window @12 launched 3m ago (ask #12)",
                "  recent:",
                "    {} ask_answered ask #13 -> skipped beta: party not handed off".format(stamp(timedelta(minutes=1))),
                "    {} ask_answered ask #12 -> launched alpha g5 [launched]".format(stamp(timedelta(minutes=3))),
                "    {} checks_failing acme/app#7 -> planned beta g3".format(stamp(timedelta(minutes=30))),
                "beta: dispatcher not configured",
            ],
        )

    def test_status_recent_is_limited_to_ten_rows(self):
        self.run_pass(False)
        now = self.ctx().now
        for number in range(12):
            self._decide("ask_answered:{}".format(number), "on", "skipped", "alpha", 2, "ask #{}".format(number), "party closed", now - timedelta(minutes=number))
        lines = dispatch_commands.status(self.ctx())
        recent = [line for line in lines if " -> skipped " in line]
        self.assertEqual(len(recent), 10)

    def test_status_through_cli(self):
        code, out, err = self.run_cli(["dispatch", "status"], None, self.repo_dir)
        self.assertEqual(code, 0)
        self.assertIn("acme: cursor not initialized | launches last hour 0/3 | mode acceptEdits", out)
        self.assertIn("beta: dispatcher not configured", out)
