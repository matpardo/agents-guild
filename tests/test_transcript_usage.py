import json
from datetime import datetime, timezone

from guild import transcript_usage
from tests.testutil import GuildTestCase
from tests.transcript_fixtures import assistant_line, write_transcript

_FAR_FUTURE = datetime(2100, 1, 1, tzinfo=timezone.utc)
_MODEL = "claude-opus-4-1"


class TranscriptUsageTests(GuildTestCase):
    def setUp(self):
        super().setUp()
        self.path = self.root / "t.jsonl"

    def _scan(self, offset, cutoff):
        return transcript_usage.scan(self.path, offset, cutoff)

    def test_single_line_fields(self):
        write_transcript(self.path, [assistant_line("m1", "2026-10-01T10:00:00.000Z", _MODEL, 1, 2, 3, 4)])
        messages, next_offset = self._scan(0, _FAR_FUTURE)
        self.assertEqual(len(messages), 1)
        message = messages[0]
        self.assertEqual(message.model, _MODEL)
        self.assertEqual(
            (message.input, message.cache_creation, message.cache_read, message.output), (1, 2, 3, 4)
        )
        self.assertEqual(next_offset, self.path.stat().st_size)

    def test_streamed_chunks_merge_with_max_per_field(self):
        write_transcript(
            self.path,
            [
                assistant_line("m1", "2026-10-01T10:00:00.000Z", _MODEL, 5, 10, 20, 1),
                assistant_line("m2", "2026-10-01T10:00:01.000Z", _MODEL, 1, 1, 1, 1),
                assistant_line("m1", "2026-10-01T10:00:02.000Z", _MODEL, 5, 10, 20, 7),
                assistant_line("m1", "2026-10-01T10:00:03.000Z", _MODEL, 5, 10, 20, 30),
            ],
        )
        messages, _ = self._scan(0, _FAR_FUTURE)
        self.assertEqual(len(messages), 2)
        first = messages[0]
        self.assertEqual((first.input, first.cache_creation, first.cache_read, first.output), (5, 10, 20, 30))
        self.assertEqual(first.timestamp, datetime(2026, 10, 1, 10, 0, 0, tzinfo=timezone.utc))

    def test_ignores_non_assistant_and_missing_usage(self):
        write_transcript(
            self.path,
            [
                json.dumps({"type": "user", "timestamp": "2026-10-01T10:00:00Z", "message": {"content": "hi"}}),
                json.dumps(
                    {
                        "type": "assistant",
                        "timestamp": "2026-10-01T10:00:00Z",
                        "message": {"id": "m1", "model": _MODEL},
                    }
                ),
                assistant_line("m2", "2026-10-01T10:00:01Z", _MODEL, 1, 0, 0, 0),
            ],
        )
        messages, _ = self._scan(0, _FAR_FUTURE)
        self.assertEqual([message.input for message in messages], [1])

    def test_skips_synthetic_and_all_zero(self):
        write_transcript(
            self.path,
            [
                assistant_line("m1", "2026-10-01T10:00:00Z", "<synthetic>", 9, 9, 9, 9),
                assistant_line("m2", "2026-10-01T10:00:01Z", _MODEL, 0, 0, 0, 0),
            ],
        )
        messages, next_offset = self._scan(0, _FAR_FUTURE)
        self.assertEqual(messages, [])
        self.assertEqual(next_offset, self.path.stat().st_size)

    def test_line_without_trailing_newline_is_not_consumed(self):
        complete = assistant_line("m1", "2026-10-01T10:00:00Z", _MODEL, 1, 0, 0, 0)
        partial = assistant_line("m2", "2026-10-01T10:00:01Z", _MODEL, 2, 0, 0, 0)
        self.path.write_text(complete + "\n" + partial)
        messages, next_offset = self._scan(0, _FAR_FUTURE)
        self.assertEqual([message.input for message in messages], [1])
        self.assertEqual(next_offset, len(complete) + 1)

    def test_malformed_complete_line_is_skipped_and_consumed(self):
        good = assistant_line("m1", "2026-10-01T10:00:00Z", _MODEL, 1, 0, 0, 0)
        self.path.write_text("{not json\n" + good + "\n")
        messages, next_offset = self._scan(0, _FAR_FUTURE)
        self.assertEqual(len(messages), 1)
        self.assertEqual(next_offset, self.path.stat().st_size)

    def test_line_newer_than_cutoff_stops_scan(self):
        old = assistant_line("m1", "2026-10-01T10:00:00Z", _MODEL, 1, 0, 0, 0)
        new = assistant_line("m2", "2026-10-01T11:00:00Z", _MODEL, 2, 0, 0, 0)
        write_transcript(self.path, [old, new])
        cutoff = datetime(2026, 10, 1, 10, 30, tzinfo=timezone.utc)
        messages, next_offset = self._scan(0, cutoff)
        self.assertEqual([message.input for message in messages], [1])
        self.assertEqual(next_offset, len(old) + 1)

    def test_rescan_from_offset_yields_only_later(self):
        old = assistant_line("m1", "2026-10-01T10:00:00Z", _MODEL, 1, 0, 0, 0)
        new = assistant_line("m2", "2026-10-01T11:00:00Z", _MODEL, 2, 0, 0, 0)
        write_transcript(self.path, [old, new])
        cutoff = datetime(2026, 10, 1, 10, 30, tzinfo=timezone.utc)
        _, next_offset = self._scan(0, cutoff)
        messages, final_offset = self._scan(next_offset, _FAR_FUTURE)
        self.assertEqual([message.input for message in messages], [2])
        self.assertEqual(final_offset, self.path.stat().st_size)

    def test_line_without_timestamp_is_consumed(self):
        line = json.dumps({"type": "assistant", "message": {"id": "m1", "model": _MODEL, "usage": {"input_tokens": 1}}})
        write_transcript(self.path, [line])
        messages, next_offset = self._scan(0, datetime(2000, 1, 1, tzinfo=timezone.utc))
        self.assertEqual(messages, [])
        self.assertEqual(next_offset, self.path.stat().st_size)
