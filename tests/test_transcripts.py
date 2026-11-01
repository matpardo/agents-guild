import json
import tempfile
import unittest
from pathlib import Path

from guild import transcripts


def _launch(task_id):
    text = "Command running in background with ID: {}. Output is being written to: /x/{}.output.".format(
        task_id, task_id
    )
    content = [{"tool_use_id": "t1", "type": "tool_result", "content": text, "is_error": False}]
    return {"type": "user", "message": {"role": "user", "content": content}}


def _notify(task_id, status):
    text = "<task-notification>\n<task-id>{}</task-id>\n<status>{}</status>\n</task-notification>".format(
        task_id, status
    )
    return {"type": "user", "message": {"role": "user", "content": text}}


class PendingBackgroundIdsTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "agent.jsonl"

    def _write(self, entries):
        self.path.write_text("\n".join(json.dumps(entry) for entry in entries) + "\n")

    def test_launched_without_notification_is_pending(self):
        self._write([{"type": "assistant", "message": {"content": []}}, _launch("b1")])
        self.assertEqual(transcripts.pending_background_ids(self.path), {"b1"})

    def test_completed_is_not_pending(self):
        self._write([_launch("b1"), _launch("b2"), _notify("b1", "completed")])
        self.assertEqual(transcripts.pending_background_ids(self.path), {"b2"})

    def test_failed_killed_and_stopped_are_terminal(self):
        self._write(
            [_launch("b1"), _launch("b2"), _launch("b3")]
            + [_notify("b1", "failed"), _notify("b2", "killed"), _notify("b3", "stopped")]
        )
        self.assertEqual(transcripts.pending_background_ids(self.path), set())

    def test_missing_file_has_nothing_pending(self):
        self.assertEqual(transcripts.pending_background_ids(self.path), set())

    def test_none_path_has_nothing_pending(self):
        self.assertEqual(transcripts.pending_background_ids(None), set())

    def test_bad_lines_are_skipped(self):
        self.path.write_text("{not json\n[1]\n" + json.dumps(_launch("b1")) + "\n")
        self.assertEqual(transcripts.pending_background_ids(self.path), {"b1"})

    def test_entry_without_message_is_skipped(self):
        self._write([{"type": "user"}, {"type": "user", "message": {"content": None}}, _launch("b1")])
        self.assertEqual(transcripts.pending_background_ids(self.path), {"b1"})


if __name__ == "__main__":
    unittest.main()
