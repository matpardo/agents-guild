import json
from datetime import timedelta, timezone
from unittest import mock

from guild import cost_collect, db, events, timeutil
from guild.cli import _build_context
from tests.testutil import GuildTestCase
from tests.transcript_fixtures import append_transcript, assistant_line, write_transcript

_MODEL = "claude-opus-4-1"
_OLD = "2020-01-01T10:00:00.000Z"


def _line(message_id, timestamp, input_tokens, output_tokens):
    return assistant_line(message_id, timestamp, _MODEL, input_tokens, 0, 0, output_tokens)


class CostCollectTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.repo_dir = self.register_project("acme", ["acme/app"])
        self.main_path = self.claude_projects_dir / "dir-a" / "sess-1.jsonl"

    def _ctx(self):
        return _build_context("sess-1", self.root)

    def _collect(self):
        ctx = self._ctx()
        cost_collect.collect(ctx)
        return ctx

    def _cost_events(self, ctx):
        return [event for event in events.all_events(ctx.conn) if event["kind"] == "cost.sampled"]

    def _samples(self, ctx):
        return ctx.conn.execute(
            "SELECT * FROM cost_samples ORDER BY session_id, day, model, party, quest, tid"
        ).fetchall()

    def _record(self, ctx, party, session_id, kind, ts, payload):
        with db.writing(ctx.conn):
            event = events.record(
                ctx.conn, timeutil.from_iso(ts), ctx.origin, party, session_id, "acme", kind, "local", payload
            )
        return event

    def _bind(self, session_id="sess-1"):
        self.run_cli(["party", "start", "alpha", "--reason", "test reason"], session_id, self.repo_dir)

    def test_main_and_subagent_count_under_parent_session(self):
        write_transcript(self.main_path, [_line("m1", _OLD, 1, 2)])
        sub = self.claude_projects_dir / "dir-a" / "sess-1" / "subagents" / "agent-x.jsonl"
        write_transcript(sub, [_line("m2", _OLD, 10, 20)])
        ctx = self._collect()
        rows = self._samples(ctx)
        self.assertEqual({row["session_id"] for row in rows}, {"sess-1"})
        self.assertEqual(sum(row["input_tokens"] for row in rows), 11)
        self.assertEqual(sum(row["output_tokens"] for row in rows), 22)

    def test_second_run_adds_no_event(self):
        write_transcript(self.main_path, [_line("m1", _OLD, 1, 2)])
        self._collect()
        ctx = self._collect()
        self.assertEqual(len(self._cost_events(ctx)), 1)

    def test_unchanged_transcript_is_not_rescanned(self):
        write_transcript(self.main_path, [_line("m1", _OLD, 1, 2)])
        self._collect()
        with mock.patch("guild.transcript_usage.scan") as scan:
            self._collect()
        scan.assert_not_called()

    def test_appended_usage_adds_delta_that_sums(self):
        write_transcript(self.main_path, [_line("m1", _OLD, 1, 2)])
        self._collect()
        append_transcript(self.main_path, [_line("m2", _OLD, 5, 7)])
        ctx = self._collect()
        self.assertEqual(len(self._cost_events(ctx)), 2)
        rows = self._samples(ctx)
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["input_tokens"], rows[0]["output_tokens"]), (6, 9))

    def test_truncated_trailing_line_picked_up_after_completion(self):
        complete = _line("m1", _OLD, 1, 2)
        partial = _line("m2", _OLD, 5, 7)
        self.main_path.parent.mkdir(parents=True)
        self.main_path.write_text(complete + "\n" + partial[:20])
        self._collect()
        with self.main_path.open("a") as handle:
            handle.write(partial[20:] + "\n")
        ctx = self._collect()
        rows = self._samples(ctx)
        self.assertEqual((rows[0]["input_tokens"], rows[0]["output_tokens"]), (6, 9))

    def test_shrunk_file_resets_cursor(self):
        write_transcript(self.main_path, [_line("m1", _OLD, 1, 2), _line("m2", _OLD, 3, 4)])
        self._collect()
        write_transcript(self.main_path, [_line("m3", _OLD, 9, 9)])
        ctx = self._collect()
        rows = self._samples(ctx)
        self.assertEqual(rows[0]["input_tokens"], 13)

    def test_missing_projects_dir_and_deleted_transcript(self):
        self.claude_projects_dir.rmdir()
        ctx = self._collect()
        self.assertEqual(self._cost_events(ctx), [])
        write_transcript(self.main_path, [_line("m1", _OLD, 1, 2)])
        self._collect()
        self.main_path.unlink()
        ctx = self._collect()
        self.assertEqual(len(self._cost_events(ctx)), 1)

    def test_bound_session_gets_party_and_project(self):
        self._bind()
        write_transcript(self.main_path, [_line("m1", _OLD, 1, 2)])
        ctx = self._collect()
        event = self._cost_events(ctx)[0]
        self.assertEqual((event["party"], event["project"], event["session_id"]), ("alpha", "acme", "sess-1"))
        self.assertEqual(self._samples(ctx)[0]["party"], "alpha")

    def test_unbound_session_has_no_party(self):
        write_transcript(self.main_path, [_line("m1", _OLD, 1, 2)])
        ctx = self._collect()
        event = self._cost_events(ctx)[0]
        self.assertIsNone(event["party"])
        self.assertIsNone(event["project"])
        self.assertEqual(self._samples(ctx)[0]["party"], "")

    def _task_event(self, ctx, kind, ts, tid):
        detail = "reason" if kind in ("task.blocked", "task.discarded") else "summary"
        payload = {"quest": "q", "tid": tid, detail: "x"}
        if kind == "task.discarded":
            payload["author"] = "alpha"
        self._record(ctx, "alpha", "sess-1", kind, ts, payload)

    def test_discard_closes_the_task_window(self):
        self._bind()
        ctx = self._ctx()
        self._task_event(ctx, "task.started", "2020-01-01T10:00:00+00:00", "T01")
        self._task_event(ctx, "task.discarded", "2020-01-01T11:00:00+00:00", "T01")
        write_transcript(
            self.main_path,
            [_line("m1", "2020-01-01T10:30:00Z", 10, 0), _line("m2", "2020-01-01T11:30:00Z", 100, 0)],
        )
        rows = {(row["quest"], row["tid"]): row["input_tokens"] for row in self._samples(self._collect())}
        self.assertEqual(rows, {("", ""): 100, ("q", "T01"): 10})

    def test_task_window_attribution(self):
        self._bind()
        ctx = self._ctx()
        self._task_event(ctx, "task.started", "2020-01-01T10:00:00+00:00", "T01")
        self._task_event(ctx, "task.done", "2020-01-01T11:00:00+00:00", "T01")
        write_transcript(
            self.main_path,
            [
                _line("m0", "2020-01-01T09:00:00Z", 1, 0),
                _line("m1", "2020-01-01T10:30:00Z", 10, 0),
                _line("m2", "2020-01-01T11:00:00Z", 100, 0),
            ],
        )
        rows = {(row["quest"], row["tid"]): row["input_tokens"] for row in self._samples(self._collect())}
        self.assertEqual(rows, {("", ""): 101, ("q", "T01"): 10})

    def test_blocked_closes_and_restart_reopens(self):
        self._bind()
        ctx = self._ctx()
        self._task_event(ctx, "task.started", "2020-01-01T10:00:00+00:00", "T01")
        self._task_event(ctx, "task.blocked", "2020-01-01T11:00:00+00:00", "T01")
        self._task_event(ctx, "task.started", "2020-01-01T12:00:00+00:00", "T01")
        write_transcript(
            self.main_path,
            [
                _line("m1", "2020-01-01T10:30:00Z", 1, 0),
                _line("m2", "2020-01-01T11:30:00Z", 10, 0),
                _line("m3", "2020-01-01T12:30:00Z", 100, 0),
            ],
        )
        rows = {(row["quest"], row["tid"]): row["input_tokens"] for row in self._samples(self._collect())}
        self.assertEqual(rows, {("", ""): 10, ("q", "T01"): 101})

    def test_overlapping_windows_latest_start_wins(self):
        self._bind()
        ctx = self._ctx()
        self._task_event(ctx, "task.started", "2020-01-01T10:00:00+00:00", "T01")
        self._task_event(ctx, "task.started", "2020-01-01T11:00:00+00:00", "T02")
        write_transcript(
            self.main_path,
            [_line("m1", "2020-01-01T10:30:00Z", 1, 0), _line("m2", "2020-01-01T11:30:00Z", 10, 0)],
        )
        rows = {(row["quest"], row["tid"]): row["input_tokens"] for row in self._samples(self._collect())}
        self.assertEqual(rows, {("q", "T01"): 1, ("q", "T02"): 10})

    def test_message_newer_than_grace_is_deferred(self):
        ctx = self._ctx()
        recent = (ctx.now - timedelta(minutes=1)).astimezone(timezone.utc).isoformat()
        write_transcript(self.main_path, [_line("m1", _OLD, 1, 0), _line("m2", recent, 5, 0)])
        ctx = self._collect()
        self.assertEqual(self._samples(ctx)[0]["input_tokens"], 1)

    def test_one_event_per_key_and_utc_day_boundary(self):
        write_transcript(
            self.main_path,
            [
                _line("m1", "2020-01-01T23:59:00Z", 1, 0),
                _line("m2", "2020-01-02T00:01:00Z", 2, 0),
                _line("m3", "2020-01-02T00:02:00Z", 4, 0),
                assistant_line("m4", "2020-01-02T00:03:00Z", "other-model", 8, 0, 0, 0),
            ],
        )
        ctx = self._collect()
        self.assertEqual(len(self._cost_events(ctx)), 3)
        days = {(row["day"], row["model"]): row["input_tokens"] for row in self._samples(ctx)}
        self.assertEqual(
            days,
            {("2020-01-01", _MODEL): 1, ("2020-01-02", _MODEL): 6, ("2020-01-02", "other-model"): 8},
        )

    def test_payload_has_only_aggregates(self):
        write_transcript(self.main_path, [_line("m1", _OLD, 1, 2)])
        payload = self._cost_events(self._collect())[0]["payload"]
        self.assertEqual(
            set(payload),
            {
                "day",
                "model",
                "quest",
                "tid",
                "account",
                "input_tokens",
                "cache_creation_tokens",
                "cache_read_tokens",
                "output_tokens",
            },
        )
        self.assertEqual(payload["account"], "")
        json.dumps(payload)
