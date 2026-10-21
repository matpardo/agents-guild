import json
import sqlite3
from datetime import timedelta

from guild import db, paths, timeutil
from guild.cli import _build_context
from guild.commands import ask as ask_commands
from guild.commands import pr as pr_commands
from guild.errors import GuildError
from tests.mq_fixtures import OPEN_VIEW, MergeQueueTestCase

_ONE_MINUTE = timedelta(minutes=1)
_TWO_HOURS = timedelta(hours=2)
_REF = "acme/app#7"


class _FakeTime:
    def __init__(self):
        self.now = timeutil.utcnow()
        self.sleeps = []
        self.on_sleep = {}

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += timedelta(seconds=seconds)
        callback = self.on_sleep.get(len(self.sleeps))
        if callback is not None:
            callback()

    def clock(self):
        return self.now


class _LockedOnce:
    def __init__(self, conn, fail_on_read):
        self._conn = conn
        self._fail_on_read = fail_on_read
        self.reads = 0

    def execute(self, sql, params):
        self.reads += 1
        if self.reads == self._fail_on_read:
            raise sqlite3.OperationalError("database is locked")
        return self._conn.execute(sql, params)


class WaitTestCase(MergeQueueTestCase):
    def setUp(self):
        super().setUp()
        self.time = _FakeTime()
        self.start_party("alpha", "sess-1")
        self.conn = db.connect(paths.db_path())
        self.addCleanup(self.conn.close)


class AskWaitTests(WaitTestCase):
    def setUp(self):
        super().setUp()
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", self.repo_dir)
        self.run_cli(["task", "add", "demo/T01", "--title", "First"], "sess-1", self.repo_dir)
        code, out, err = self.run_cli(
            ["ask", "Which?", "--context", "ctx", "--ref", "task:demo/T01"], "sess-1", self.repo_dir
        )
        self.assertEqual(code, 0, err)

    def _wait(self, ask_id, timeout):
        return ask_commands.wait(self.conn, ask_id, timeout, self.time.sleep, self.time.clock)

    def _answer(self):
        self.run_cli(["answer", "1", "secret-text"], None, None)

    def test_answered_between_polls(self):
        self.time.on_sleep[2] = self._answer
        line, code = self._wait(1, _TWO_HOURS)
        self.assertEqual((line, code), ("ask #1 answered: read it with guild asks 1", 0))
        self.assertNotIn("secret-text", line)
        self.assertEqual(len(self.time.sleeps), 2)

    def test_dismissed(self):
        self.time.on_sleep[1] = lambda: self.run_cli(["dismiss", "1"], None, None)
        self.assertEqual(self._wait(1, _TWO_HOURS), ("ask #1 dismissed", 0))

    def test_already_answered_returns_without_sleeping(self):
        self._answer()
        self.assertEqual(self._wait(1, _TWO_HOURS)[1], 0)
        self.assertEqual(self.time.sleeps, [])

    def test_unknown_id_raises(self):
        with self.assertRaises(GuildError) as raised:
            self._wait(99, _TWO_HOURS)
        self.assertEqual(raised.exception.exit_code, 1)
        self.assertIn("unknown ask #99", str(raised.exception))

    def test_timeout_exits_three(self):
        self.assertEqual(self._wait(1, _ONE_MINUTE), ("ask #1 still open after 1m", 3))
        self.assertEqual(len(self.time.sleeps), 4)

    def test_poll_retries_after_a_locked_read(self):
        locked = _LockedOnce(self.conn, 2)
        self.time.on_sleep[1] = self._answer
        result = ask_commands.wait(locked, 1, _TWO_HOURS, self.time.sleep, self.time.clock)
        self.assertEqual(result[1], 0)
        self.assertEqual(len(self.time.sleeps), 2)

    def test_cli_unknown_id_exits_one(self):
        code, out, err = self.run_cli(["ask", "wait", "99"], "sess-1", self.repo_dir)
        self.assertEqual(code, 1)
        self.assertIn("unknown ask #99", err)

    def test_cli_wait_rejects_context(self):
        code, out, err = self.run_cli(["ask", "wait", "1", "--context", "x"], "sess-1", self.repo_dir)
        self.assertEqual(code, 1)

    def test_cli_wait_rejects_non_integer_id(self):
        code, out, err = self.run_cli(["ask", "wait", "abc"], "sess-1", self.repo_dir)
        self.assertEqual(code, 1)

    def test_cli_already_answered_exits_zero(self):
        self._answer()
        code, out, err = self.run_cli(["ask", "wait", "1"], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        self.assertIn("ask #1 answered", out)
        self.assertNotIn("secret-text", out)

    def test_cli_create_without_context_exits_one(self):
        code, out, err = self.run_cli(["ask", "Which?"], "sess-1", self.repo_dir)
        self.assertEqual(code, 1)
        self.assertIn("--context is required", err)

    def test_cli_create_rejects_timeout(self):
        code, out, err = self.run_cli(["ask", "Which?", "--context", "c", "--timeout", "1h"], "sess-1", self.repo_dir)
        self.assertEqual(code, 1)

    def test_cli_extra_argument_on_create_exits_one(self):
        code, out, err = self.run_cli(["ask", "Which?", "1", "--context", "c"], "sess-1", self.repo_dir)
        self.assertEqual(code, 1)
        self.assertIn("unexpected extra argument", err)


_NOTICE_BODY = "Usage notice: budget reached"


def _entry(login, body, **extra):
    return dict({"author": {"login": login}, "body": body}, **extra)


class PrWaitTests(WaitTestCase):
    def setUp(self):
        super().setUp()
        self.run_cli(["quest", "add", "demo", "--title", "Demo", "--no-epic"], "sess-1", self.repo_dir)
        self.run_cli(["task", "add", "demo/T01", "--title", "First"], "sess-1", self.repo_dir)
        self.track("sess-1", 7, "demo/T01", "ready")
        self._set_project_config(
            {"human_ready": {"notice_comments": [{"author": "notifier", "pattern": "^Usage notice"}]}}
        )
        self.view = dict(
            OPEN_VIEW,
            author={"login": "me"},
            commits=[{"committedDate": "2026-10-20T10:00:00Z"}],
            comments=[],
            reviews=[],
        )
        self._publish()

    def _publish(self, **extra):
        self.view.update(extra)
        self.write_gh_fixture("view_acme-app_7", self.view)
        self.assertEqual(self.sync_gh("sess-1")[0], 0)

    def _later(self, **extra):
        return lambda: self._publish(**extra)

    def _wait(self, ref, timeout):
        return pr_commands.wait(self.conn, ref, timeout, self.time.sleep, self.time.clock)

    def test_wakes_on_comment_by_another_author(self):
        self.time.on_sleep[2] = self._later(comments=[_entry("human", "hi", createdAt="2026-10-20T11:00:00Z")])
        self.assertEqual(self._wait(_REF, _TWO_HOURS), ("acme/app#7 new comment or review", 0))
        self.assertEqual(len(self.time.sleeps), 2)

    def test_wakes_on_comment_before_a_newer_head(self):
        self.time.on_sleep[1] = self._later(
            comments=[_entry("human", "hi", createdAt="2026-10-20T09:00:00Z")],
            commits=[{"committedDate": "2026-10-20T12:00:00Z"}],
        )
        self.assertEqual(self._wait(_REF, _TWO_HOURS)[1], 0)

    def test_ignores_the_pr_author(self):
        self.time.on_sleep[1] = self._later(comments=[_entry("me", "mine")])
        self.assertEqual(self._wait(_REF, _ONE_MINUTE), ("acme/app#7 no change in 1m", 3))

    def test_ignores_notice_only_bot_comment(self):
        self.time.on_sleep[1] = self._later(comments=[_entry("notifier", _NOTICE_BODY)])
        self.assertEqual(self._wait(_REF, _ONE_MINUTE)[1], 3)

    def test_wakes_on_review_by_rule_author_with_other_body(self):
        self.time.on_sleep[1] = self._later(reviews=[_entry("notifier", "LGTM")])
        self.assertEqual(self._wait(_REF, _TWO_HOURS)[1], 0)

    def test_wakes_when_checks_go_pending_to_done(self):
        self._publish(statusCheckRollup=[{"status": "IN_PROGRESS"}, {"status": "IN_PROGRESS"}])
        self.time.on_sleep[1] = self._later(statusCheckRollup=[{"conclusion": "SUCCESS"}, {"conclusion": "SUCCESS"}])
        line, code = self._wait(_REF, _TWO_HOURS)
        self.assertEqual((line, code), ("acme/app#7 checks finished: 0 failing, 2 passing", 0))

    def test_checks_never_pending_do_not_wake(self):
        self.time.on_sleep[1] = self._later(statusCheckRollup=[{"conclusion": "FAILURE"}])
        self.assertEqual(self._wait(_REF, _ONE_MINUTE)[1], 3)

    def test_wakes_on_merge(self):
        self.time.on_sleep[1] = self._later(state="MERGED", mergedAt="2026-10-20T12:00:00Z")
        self.assertEqual(self._wait(_REF, _TWO_HOURS), ("acme/app#7 merged", 0))

    def test_wakes_on_close(self):
        self.time.on_sleep[1] = self._later(state="CLOSED")
        self.assertEqual(self._wait(_REF, _TWO_HOURS), ("acme/app#7 closed", 0))

    def test_already_merged_returns_without_sleeping(self):
        self._publish(state="MERGED", mergedAt="2026-10-20T12:00:00Z")
        self.assertEqual(self._wait(_REF, _TWO_HOURS), ("acme/app#7 merged", 0))
        self.assertEqual(self.time.sleeps, [])

    def test_untracked_ref_raises(self):
        with self.assertRaises(GuildError) as raised:
            self._wait("acme/app#99", _TWO_HOURS)
        self.assertEqual(raised.exception.exit_code, 1)
        self.assertIn("not tracked", str(raised.exception))

    def test_invalid_ref_raises(self):
        with self.assertRaises(GuildError):
            self._wait("nonsense", _TWO_HOURS)

    def test_no_sync_for_thirty_minutes_exits_four(self):
        line, code = self._wait(_REF, _TWO_HOURS)
        self.assertEqual(code, 4)
        self.assertEqual(line, "acme/app#7: no sync for 30m: run guild sync --source gh or install guild sync-timer")
        self.assertEqual(len(self.time.sleeps), 121)

    def test_timeout_while_syncs_keep_running(self):
        counter = {"n": 0}

        def touch():
            counter["n"] += 1
            raw = sqlite3.connect(str(paths.db_path()))
            raw.execute("UPDATE prs SET synced_at = ? WHERE number = 7", ("tick-{}".format(counter["n"]),))
            raw.commit()
            raw.close()

        for call in range(1, 13):
            self.time.on_sleep[call] = touch
        self.assertEqual(self._wait(_REF, timedelta(minutes=3)), ("acme/app#7 no change in 3m", 3))

    def test_cli_untracked_exits_one(self):
        code, out, err = self.run_cli(["pr", "wait", "acme/app#99"], "sess-1", self.repo_dir)
        self.assertEqual(code, 1)
        self.assertIn("not tracked", err)

    def test_cli_merged_exits_zero(self):
        self._publish(state="MERGED", mergedAt="2026-10-20T12:00:00Z")
        code, out, err = self.run_cli(["pr", "wait", _REF], "sess-1", self.repo_dir)
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "acme/app#7 merged")
