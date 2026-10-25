import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from guild import background


class BackgroundTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.state_dir = Path(tmp.name)
        self.now = datetime.now(timezone.utc)

    def _labels(self):
        return background.labels(self.state_dir, "sess-1", self.now)

    def test_no_directory_has_no_labels(self):
        self.assertEqual(self._labels(), [])

    def test_live_pr_marker_is_listed_and_cleared(self):
        key = background.pr_key(os.getpid())
        background.mark(self.state_dir, "sess-1", key, "pr acme/app#7")
        self.assertEqual(self._labels(), ["pr acme/app#7"])
        background.clear(self.state_dir, "sess-1", key)
        self.assertEqual(self._labels(), [])

    def test_clear_missing_marker_is_a_no_op(self):
        background.clear(self.state_dir, "sess-1", background.pr_key(1))

    def test_dead_pr_marker_is_dropped_and_deleted(self):
        key = background.pr_key(2 ** 22 + 12345)
        background.mark(self.state_dir, "sess-1", key, "pr acme/app#7")
        self.assertEqual(self._labels(), [])
        self.assertFalse((self.state_dir / "background" / "sess-1" / key).exists())

    def test_subagents_collapse_into_one_label(self):
        background.mark(self.state_dir, "sess-1", background.subagent_key("a1"), "a1")
        background.mark(self.state_dir, "sess-1", background.subagent_key("a2"), "a2")
        self.assertEqual(self._labels(), ["2 subagents"])

    def test_stale_subagent_marker_expires(self):
        key = background.subagent_key("a1")
        background.mark(self.state_dir, "sess-1", key, "a1")
        later = datetime.fromtimestamp(self.now.timestamp() + 3 * 60 * 60, timezone.utc)
        self.assertEqual(background.labels(self.state_dir, "sess-1", later), [])

    def _subagent_with_meta(self, content):
        meta = self.state_dir / "agent-a1.meta.json"
        if content is not None:
            meta.write_text(content)
        background.mark(self.state_dir, "sess-1", background.subagent_key("a1"), str(meta))
        return background.subagent_key("a1")

    def test_finished_subagent_marker_is_dropped_and_deleted(self):
        key = self._subagent_with_meta(json.dumps({"finished": True}))
        self.assertEqual(self._labels(), [])
        self.assertFalse((self.state_dir / "background" / "sess-1" / key).exists())

    def test_unfinished_subagent_meta_stays_live(self):
        self._subagent_with_meta(json.dumps({"agentType": "x"}))
        self.assertEqual(self._labels(), ["1 subagents"])

    def test_missing_subagent_meta_stays_live(self):
        self._subagent_with_meta(None)
        self.assertEqual(self._labels(), ["1 subagents"])

    def test_invalid_subagent_meta_stays_live(self):
        self._subagent_with_meta("{not json")
        self.assertEqual(self._labels(), ["1 subagents"])

    def test_clear_subagents_keeps_pr_markers(self):
        background.mark(self.state_dir, "sess-1", background.subagent_key("a1"), "a1")
        background.mark(self.state_dir, "sess-1", background.pr_key(os.getpid()), "pr x#1")
        background.clear_subagents(self.state_dir, "sess-1")
        self.assertEqual(self._labels(), ["pr x#1"])

    def test_clear_subagents_without_directory_is_a_no_op(self):
        background.clear_subagents(self.state_dir, "sess-1")
